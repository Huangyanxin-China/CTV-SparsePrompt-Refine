import heapq

import numpy as np
from scipy import ndimage

from .geometry import (
    graphcut_contact_refine,
    keep_seed_connected,
    sparse_hu_likelihood,
    sparse_sdf_propagation,
)


def sparse_seed_from_slices(target_mask, annotated_z):
    seed = np.zeros(target_mask.shape, dtype=bool)
    seed[np.array(annotated_z, dtype=int)] = target_mask[np.array(annotated_z, dtype=int)]
    return seed


def ball_structure(radius):
    radius = int(max(radius, 0))
    if radius <= 0:
        return np.ones((1, 1, 1), dtype=bool)
    zz, yy, xx = np.ogrid[-radius : radius + 1, -radius : radius + 1, -radius : radius + 1]
    return (zz * zz + yy * yy + xx * xx) <= radius * radius


def estimate_sparse_volume(target_mask, annotated_z, scale=1.0):
    annotated_z = np.sort(np.array(annotated_z, dtype=int))
    areas = target_mask.reshape(target_mask.shape[0], -1).sum(axis=1).astype(np.float32)
    if annotated_z.size == 0:
        return 0
    if annotated_z.size == 1:
        return int(max(areas[int(annotated_z[0])], 1) * float(scale))
    z_range = np.arange(int(annotated_z[0]), int(annotated_z[-1]) + 1, dtype=np.float32)
    interp = np.interp(z_range, annotated_z.astype(np.float32), areas[annotated_z])
    return int(max(float(interp.sum()) * float(scale), float(areas[annotated_z].sum())))


def connectivity_valid_region(
    label,
    sparse_seed,
    lung_label=1,
    avoid_labels=(2, 3, 4),
    lung_radius=24.0,
    hard_exclude_oar=True,
):
    label = label.astype(np.int16)
    valid = np.ones(label.shape, dtype=bool)
    avoid = np.isin(label, np.array(avoid_labels, dtype=np.int16))
    if hard_exclude_oar:
        valid &= ~avoid

    lung = label == int(lung_label)
    if lung.any() and float(lung_radius) >= 0:
        dist_to_lung = ndimage.distance_transform_edt(~lung).astype(np.float32)
        valid &= dist_to_lung <= float(lung_radius)

    valid |= sparse_seed.astype(bool)
    return valid.astype(bool)


def connectivity_cost_volume(
    image,
    label,
    target_mask,
    annotated_z,
    prior_mask,
    valid_region,
    lung_label=1,
    avoid_labels=(2, 3, 4),
    sdf_tau=5.0,
    hu_sigma=80.0,
    grad_sigma=1.0,
    lung_radius=24.0,
    soft_oar_margin=4.0,
    shape_weight=0.35,
    hu_weight=0.30,
    lung_weight=0.20,
    edge_weight=0.10,
    soft_oar_weight=0.25,
    z_weight=0.05,
    surface_like=None,
    surface_weight=0.0,
):
    image = image.astype(np.float32)
    target_mask = target_mask.astype(bool)
    valid_region = valid_region.astype(bool)
    prior_sdf = sparse_sdf_propagation(target_mask, annotated_z, shrink_per_slice=1.0, max_z_distance=-1)
    shape_prob = 1.0 / (1.0 + np.exp(-np.clip(prior_sdf / max(float(sdf_tau), 1e-3), -20.0, 20.0)))
    shape_cost = 1.0 - shape_prob.astype(np.float32)

    hu_like = sparse_hu_likelihood(image, target_mask, annotated_z, min_sigma=max(float(hu_sigma) * 0.5, 20.0))
    hu_cost = 1.0 - hu_like.astype(np.float32)

    lung_cost = np.zeros_like(image, dtype=np.float32)
    lung = label == int(lung_label)
    if lung.any() and float(lung_radius) > 0:
        dist_to_lung = ndimage.distance_transform_edt(~lung).astype(np.float32)
        lung_cost = np.clip(dist_to_lung / float(lung_radius), 0.0, 1.0)

    smoothed = ndimage.gaussian_filter(image, sigma=max(float(grad_sigma), 0.0))
    grad = np.sqrt(sum(g * g for g in np.gradient(smoothed))).astype(np.float32)
    p95 = float(np.percentile(grad, 95))
    if p95 > 1e-6:
        grad = np.clip(grad / p95, 0.0, 2.0) / 2.0

    annotated_z = np.array(annotated_z, dtype=np.float32)
    z = np.arange(image.shape[0], dtype=np.float32)
    dz = np.min(np.abs(z[:, None] - annotated_z[None, :]), axis=1)
    z_cost = dz[:, None, None] / max(float(image.shape[0]), 1.0)

    oar_penalty = np.zeros_like(image, dtype=np.float32)
    oar = np.isin(label.astype(np.int16), np.array(avoid_labels, dtype=np.int16))
    if oar.any() and float(soft_oar_margin) > 0:
        dist_to_oar = ndimage.distance_transform_edt(~oar).astype(np.float32)
        oar_penalty = np.exp(-(dist_to_oar * dist_to_oar) / (2.0 * float(soft_oar_margin) ** 2)).astype(np.float32)
        oar_penalty[oar] = 1.0

    total = (
        float(shape_weight)
        + float(hu_weight)
        + float(lung_weight)
        + float(edge_weight)
        + float(soft_oar_weight)
        + float(z_weight)
        + float(surface_weight)
    )
    cost = (
        float(shape_weight) * shape_cost
        + float(hu_weight) * hu_cost
        + float(lung_weight) * lung_cost
        + float(edge_weight) * grad
        + float(soft_oar_weight) * oar_penalty
        + float(z_weight) * z_cost
    ) / max(total, 1e-6)
    if surface_like is not None and float(surface_weight) > 0:
        surface_cost = 1.0 - np.clip(surface_like.astype(np.float32), 0.0, 1.0)
        cost = cost + float(surface_weight) * surface_cost / max(total, 1e-6)
    cost = np.clip(cost, 0.0, 10.0).astype(np.float32)
    cost[~valid_region] = np.inf
    return cost


def lung_surface_completion_prior(
    image,
    label,
    target_mask,
    annotated_z,
    lung_label=1,
    avoid_labels=(2, 3, 4),
    close_radius=8,
    support_dilate=4,
    band=10.0,
    hu_sigma=80.0,
    hu_weight=0.35,
    hard_exclude_oar=True,
):
    """Estimate CTV-favorable regions from local lung-surface completion.

    The prior does not use the full target mask except on sparse annotated
    slices. It completes local defects in label=1, treats completed-minus-lung
    as a surface-defect hypothesis, and optionally boosts areas whose HU is
    compatible with sparse CTV.
    """
    lung = label == int(lung_label)
    if not lung.any():
        zeros = np.zeros(label.shape, dtype=np.float32)
        return zeros, np.zeros(label.shape, dtype=bool)

    close_radius = int(max(close_radius, 1))
    support_dilate = int(max(support_dilate, 0))
    structure = ball_structure(close_radius)
    completed = ndimage.binary_closing(lung, structure=structure)
    completed = ndimage.binary_fill_holes(completed)
    defect = completed & (~lung)

    oar = np.isin(label.astype(np.int16), np.array(avoid_labels, dtype=np.int16))
    if hard_exclude_oar:
        defect &= ~oar

    sparse_seed = sparse_seed_from_slices(target_mask, annotated_z)
    defect |= sparse_seed
    if support_dilate > 0:
        support = ndimage.binary_dilation(defect, structure=ball_structure(support_dilate))
    else:
        support = defect.copy()

    dist_to_defect = ndimage.distance_transform_edt(~defect).astype(np.float32)
    surface_like = np.exp(-(dist_to_defect * dist_to_defect) / (2.0 * max(float(band), 1e-3) ** 2))
    surface_like *= support.astype(np.float32)

    if float(hu_weight) > 0:
        hu_like = sparse_hu_likelihood(image, target_mask, annotated_z, min_sigma=max(float(hu_sigma) * 0.5, 20.0))
        surface_like = (1.0 - float(hu_weight)) * surface_like + float(hu_weight) * surface_like * hu_like

    if hard_exclude_oar:
        surface_like[oar] = 0.0
        support &= ~oar
    support |= sparse_seed
    surface_like[sparse_seed] = 1.0
    return np.clip(surface_like, 0.0, 1.0).astype(np.float32), support.astype(bool)


def _bbox_from_masks(masks, shape, margin_zyx=(2, 32, 32)):
    coords = []
    for mask in masks:
        pts = np.argwhere(mask)
        if pts.size:
            coords.append(pts)
    if not coords:
        return tuple(slice(0, s) for s in shape)
    pts = np.concatenate(coords, axis=0)
    margin = np.array(margin_zyx, dtype=int)
    start = np.maximum(pts.min(axis=0) - margin, 0)
    stop = np.minimum(pts.max(axis=0) + margin + 1, np.array(shape))
    return tuple(slice(int(a), int(b)) for a, b in zip(start, stop))


def _centroid_line(mask_a, mask_b, shape):
    out = np.zeros(shape, dtype=bool)
    ca = np.argwhere(mask_a)
    cb = np.argwhere(mask_b)
    if ca.size == 0 or cb.size == 0:
        return out
    a = ca.mean(axis=0)
    b = cb.mean(axis=0)
    steps = int(max(np.abs(b - a).max(), 1)) + 1
    for t in np.linspace(0.0, 1.0, steps):
        p = np.round((1.0 - t) * a + t * b).astype(int)
        p = np.clip(p, 0, np.array(shape) - 1)
        out[tuple(p)] = True
    return out


def _dijkstra_path(cost, valid, source, target, z_step_weight=1.0):
    valid = valid.astype(bool) & np.isfinite(cost)
    source = source.astype(bool) & valid
    target = target.astype(bool) & valid
    if not source.any() or not target.any():
        return np.zeros(valid.shape, dtype=bool), False

    shape = valid.shape
    yz = shape[1] * shape[2]
    n = int(np.prod(shape))
    valid_f = valid.ravel()
    target_f = target.ravel()
    cost_f = cost.ravel()
    dist = np.full(n, np.inf, dtype=np.float32)
    parent = np.full(n, -1, dtype=np.int64)
    heap = []
    for idx in np.flatnonzero(source.ravel()):
        dist[idx] = 0.0
        heapq.heappush(heap, (0.0, int(idx)))

    found = -1
    while heap:
        d, idx = heapq.heappop(heap)
        if d > float(dist[idx]) + 1e-6:
            continue
        if target_f[idx]:
            found = idx
            break

        z = idx // yz
        rem = idx - z * yz
        y = rem // shape[2]
        x = rem - y * shape[2]
        neigh = []
        if z > 0:
            neigh.append((idx - yz, z_step_weight))
        if z + 1 < shape[0]:
            neigh.append((idx + yz, z_step_weight))
        if y > 0:
            neigh.append((idx - shape[2], 1.0))
        if y + 1 < shape[1]:
            neigh.append((idx + shape[2], 1.0))
        if x > 0:
            neigh.append((idx - 1, 1.0))
        if x + 1 < shape[2]:
            neigh.append((idx + 1, 1.0))

        for nb, step in neigh:
            if not valid_f[nb]:
                continue
            nd = float(d) + float(step) * (1.0 + float(cost_f[nb]))
            if nd < float(dist[nb]):
                dist[nb] = nd
                parent[nb] = idx
                heapq.heappush(heap, (nd, int(nb)))

    path = np.zeros(shape, dtype=bool)
    if found < 0:
        return path, False
    cur = int(found)
    while cur >= 0:
        path.ravel()[cur] = True
        cur = int(parent[cur])
    return path, True


def geodesic_backbone(
    cost,
    valid_region,
    sparse_seed,
    annotated_z,
    bridge_radius=2,
    crop_margin_yx=36,
    z_margin=1,
    z_step_weight=1.0,
):
    annotated_z = np.sort(np.array(annotated_z, dtype=int))
    backbone = sparse_seed.astype(bool).copy()
    if annotated_z.size <= 1:
        return backbone

    for z in annotated_z:
        z = int(z)
        labeled, num = ndimage.label(sparse_seed[z])
        if num <= 1:
            continue
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0
        main_id = int(np.argmax(sizes))
        main = np.zeros_like(backbone, dtype=bool)
        main[z] = labeled == main_id
        for comp_id in range(1, num + 1):
            if comp_id == main_id:
                continue
            comp = np.zeros_like(backbone, dtype=bool)
            comp[z] = labeled == comp_id
            slc = _bbox_from_masks(
                [main, comp],
                shape=backbone.shape,
                margin_zyx=(0, int(crop_margin_yx), int(crop_margin_yx)),
            )
            valid_c = valid_region[slc].copy()
            src_c = comp[slc]
            dst_c = main[slc] | backbone[slc]
            valid_c |= src_c | dst_c
            cost_c = cost[slc].copy()
            cost_c[~valid_c] = np.inf
            path_c, ok = _dijkstra_path(cost_c, valid_c, src_c, dst_c, z_step_weight=z_step_weight)
            if not ok:
                path = _centroid_line(comp, main | backbone, backbone.shape)
            else:
                path = np.zeros_like(backbone, dtype=bool)
                path[slc] = path_c
            backbone |= path

    for z0, z1 in zip(annotated_z[:-1], annotated_z[1:]):
        src = np.zeros_like(backbone, dtype=bool)
        dst = np.zeros_like(backbone, dtype=bool)
        src[int(z0)] = backbone[int(z0)]
        dst[int(z1)] = backbone[int(z1)]
        if not src.any() or not dst.any():
            continue
        slc = _bbox_from_masks(
            [src, dst],
            shape=backbone.shape,
            margin_zyx=(int(z_margin), int(crop_margin_yx), int(crop_margin_yx)),
        )
        valid_c = valid_region[slc].copy()
        src_c = src[slc]
        dst_c = dst[slc]
        valid_c |= src_c | dst_c
        cost_c = cost[slc].copy()
        cost_c[~valid_c] = np.inf
        path_c, ok = _dijkstra_path(cost_c, valid_c, src_c, dst_c, z_step_weight=z_step_weight)
        if not ok:
            path = _centroid_line(src, dst, backbone.shape)
        else:
            path = np.zeros_like(backbone, dtype=bool)
            path[slc] = path_c
        backbone |= path

    if int(bridge_radius) > 0:
        backbone = ndimage.binary_dilation(backbone, structure=ball_structure(int(bridge_radius)))
        backbone &= valid_region | sparse_seed
        backbone |= sparse_seed
    return backbone.astype(bool)


def connected_region_grow(seed_mask, candidate_region, cost, target_voxels, max_cost=np.inf):
    seed_mask = seed_mask.astype(bool)
    candidate_region = candidate_region.astype(bool) & np.isfinite(cost)
    region = seed_mask.copy()
    region &= candidate_region | seed_mask
    candidate_region |= region
    target_voxels = int(max(target_voxels, int(region.sum())))
    target_voxels = int(min(target_voxels, int(candidate_region.sum())))
    region_count = int(region.sum())
    if region_count >= target_voxels:
        return region

    shape = region.shape
    yz = shape[1] * shape[2]
    visited = region.copy()
    heap = []

    def push_neighbors(idx):
        z = idx // yz
        rem = idx - z * yz
        y = rem // shape[2]
        x = rem - y * shape[2]
        neigh = []
        if z > 0:
            neigh.append(idx - yz)
        if z + 1 < shape[0]:
            neigh.append(idx + yz)
        if y > 0:
            neigh.append(idx - shape[2])
        if y + 1 < shape[1]:
            neigh.append(idx + shape[2])
        if x > 0:
            neigh.append(idx - 1)
        if x + 1 < shape[2]:
            neigh.append(idx + 1)
        cand_f = candidate_region.ravel()
        visited_f = visited.ravel()
        cost_f = cost.ravel()
        for nb in neigh:
            if visited_f[nb] or not cand_f[nb]:
                continue
            c = float(cost_f[nb])
            if c > float(max_cost):
                continue
            visited_f[nb] = True
            heapq.heappush(heap, (c, int(nb)))

    for idx in np.flatnonzero(region.ravel()):
        push_neighbors(int(idx))

    region_f = region.ravel()
    while heap and region_count < target_voxels:
        _, idx = heapq.heappop(heap)
        if region_f[idx]:
            continue
        region_f[idx] = True
        region_count += 1
        push_neighbors(int(idx))
    return region.astype(bool)


def repair_connected_shape(
    mask,
    seed_mask,
    valid_region,
    close_radius=2,
    slice_close_radius=3,
    fill_holes=True,
):
    mask = mask.astype(bool)
    seed_mask = seed_mask.astype(bool)
    valid_region = valid_region.astype(bool)
    out = mask | seed_mask
    if int(close_radius) > 0:
        out = ndimage.binary_closing(out, structure=ball_structure(int(close_radius)))
        out |= seed_mask
    if int(slice_close_radius) > 0 or bool(fill_holes):
        structure2d = np.ones((2 * int(max(slice_close_radius, 0)) + 1, 2 * int(max(slice_close_radius, 0)) + 1), dtype=bool)
        for z in range(out.shape[0]):
            sl = out[z]
            if not sl.any():
                continue
            if int(slice_close_radius) > 0:
                sl = ndimage.binary_closing(sl, structure=structure2d)
            if fill_holes:
                sl = ndimage.binary_fill_holes(sl)
            out[z] = sl
    out &= valid_region | seed_mask
    out |= seed_mask
    out = keep_seed_connected(out, seed_mask)
    out |= seed_mask
    return out.astype(bool)


def connectivity_first_pseudo(
    image,
    label,
    target_mask,
    annotated_z,
    method="conn_grow_hu_lung",
    lung_label=1,
    avoid_labels=(2, 3, 4),
    lung_radius=24.0,
    bridge_radius=2,
    crop_margin_yx=36,
    z_margin=1,
    volume_scale=1.0,
    volume_mode="interp",
    z_extension=0,
    hard_exclude_oar=True,
    sdf_tau=5.0,
    hu_sigma=80.0,
    grad_sigma=1.0,
    soft_oar_margin=4.0,
    shape_weight=0.35,
    hu_weight=0.30,
    lung_weight=0.20,
    edge_weight=0.10,
    soft_oar_weight=0.25,
    z_weight=0.05,
    grow_max_cost=np.inf,
    gc_solver="auto",
    gc_neighbor_weight=0.55,
    gc_threshold=0.5,
    surface_close_radius=8,
    surface_support_dilate=4,
    surface_band=10.0,
    surface_weight=0.45,
    surface_hu_weight=0.35,
    repair_close_radius=2,
    repair_slice_close_radius=3,
):
    target_mask = target_mask.astype(bool)
    annotated_z = np.sort(np.array(annotated_z, dtype=int))
    sparse_seed = sparse_seed_from_slices(target_mask, annotated_z)
    prior_sdf = sparse_sdf_propagation(target_mask, annotated_z, shrink_per_slice=1.0, max_z_distance=-1)
    prior_mask = prior_sdf >= 0
    surface_methods = (
        "conn_surface",
        "conn_surface_hu",
        "conn_surface_smooth",
        "conn_surface_hu_smooth",
        "conn_surface_hu_gc",
        "conn_surface_fill",
        "conn_surface_hu_fill",
    )
    use_surface = method in surface_methods

    valid = connectivity_valid_region(
        label=label,
        sparse_seed=sparse_seed,
        lung_label=lung_label,
        avoid_labels=avoid_labels,
        lung_radius=-1 if use_surface else lung_radius,
        hard_exclude_oar=hard_exclude_oar,
    )

    use_hu = method in (
        "conn_grow_hu",
        "conn_grow_hu_lung",
        "conn_grow_hu_lung_softoar",
        "conn_gc_hu_lung",
        "conn_gc_hu_lung_softoar",
        "conn_surface_hu",
        "conn_surface_hu_smooth",
        "conn_surface_hu_gc",
        "conn_surface_hu_fill",
    )
    use_lung = method in (
        "conn_grow_lung",
        "conn_grow_hu_lung",
        "conn_grow_hu_lung_softoar",
        "conn_gc_hu_lung",
        "conn_gc_hu_lung_softoar",
    )
    use_soft_oar = method in ("conn_grow_hu_lung_softoar", "conn_gc_hu_lung_softoar")

    surface_like = None
    surface_support = None
    if use_surface:
        surface_like, surface_support = lung_surface_completion_prior(
            image=image,
            label=label,
            target_mask=target_mask,
            annotated_z=annotated_z,
            lung_label=lung_label,
            avoid_labels=avoid_labels,
            close_radius=surface_close_radius,
            support_dilate=surface_support_dilate,
            band=surface_band,
            hu_sigma=hu_sigma,
            hu_weight=surface_hu_weight if use_hu else 0.0,
            hard_exclude_oar=hard_exclude_oar,
        )
        valid &= surface_support | sparse_seed | prior_mask

    cost = connectivity_cost_volume(
        image=image,
        label=label,
        target_mask=target_mask,
        annotated_z=annotated_z,
        prior_mask=prior_mask,
        valid_region=valid,
        lung_label=lung_label,
        avoid_labels=avoid_labels,
        sdf_tau=sdf_tau,
        hu_sigma=hu_sigma,
        grad_sigma=grad_sigma,
        lung_radius=lung_radius,
        soft_oar_margin=soft_oar_margin,
        shape_weight=shape_weight,
        hu_weight=hu_weight if use_hu else 0.0,
        lung_weight=lung_weight if use_lung else 0.0,
        edge_weight=edge_weight,
        soft_oar_weight=soft_oar_weight if use_soft_oar else 0.0,
        z_weight=z_weight,
        surface_like=surface_like,
        surface_weight=surface_weight if use_surface else 0.0,
    )

    backbone = geodesic_backbone(
        cost=cost,
        valid_region=valid,
        sparse_seed=sparse_seed,
        annotated_z=annotated_z,
        bridge_radius=bridge_radius,
        crop_margin_yx=crop_margin_yx,
        z_margin=z_margin,
    )
    backbone |= sparse_seed
    backbone = keep_seed_connected(backbone, sparse_seed)

    if method == "conn_backbone":
        pseudo = backbone
    else:
        if volume_mode == "prior":
            target_voxels = int(prior_mask.sum() * float(volume_scale))
        elif volume_mode == "max":
            target_voxels = int(max(prior_mask.sum(), estimate_sparse_volume(target_mask, annotated_z, scale=1.0)) * float(volume_scale))
        else:
            target_voxels = estimate_sparse_volume(target_mask, annotated_z, scale=volume_scale)

        zmin = max(int(annotated_z[0]) - int(z_extension), 0)
        zmax = min(int(annotated_z[-1]) + int(z_extension), target_mask.shape[0] - 1)
        z_region = np.zeros(target_mask.shape, dtype=bool)
        z_region[zmin : zmax + 1] = True
        candidate = valid & z_region
        if use_surface and surface_support is not None:
            candidate &= surface_support | prior_mask | backbone | sparse_seed
        candidate |= backbone | sparse_seed
        if method in ("conn_surface_fill", "conn_surface_hu_fill"):
            pseudo = keep_seed_connected(candidate, backbone | sparse_seed)
        else:
            pseudo = connected_region_grow(
                seed_mask=backbone,
                candidate_region=candidate,
                cost=cost,
                target_voxels=target_voxels,
                max_cost=grow_max_cost,
            )

        if method in ("conn_gc_hu_lung", "conn_gc_hu_lung_softoar", "conn_surface_hu_gc"):
            pseudo, _ = graphcut_contact_refine(
                image=image,
                label=label,
                prior_mask=pseudo,
                target_mask=target_mask,
                annotated_z=annotated_z,
                valid_region=valid,
                use_lung_prior=True,
                use_hu_prior=True,
                use_soft_oar=method in ("conn_gc_hu_lung_softoar", "conn_surface_hu_gc"),
                hu_sigma=hu_sigma,
                sdf_tau=sdf_tau,
                neighbor_weight=gc_neighbor_weight,
                threshold=gc_threshold,
                solver=gc_solver,
            )
            pseudo |= backbone

        if method in (
            "conn_surface_smooth",
            "conn_surface_hu_smooth",
            "conn_surface_hu_gc",
            "conn_surface_fill",
            "conn_surface_hu_fill",
        ):
            repair_valid = connectivity_valid_region(
                label=label,
                sparse_seed=sparse_seed,
                lung_label=lung_label,
                avoid_labels=avoid_labels,
                lung_radius=-1,
                hard_exclude_oar=hard_exclude_oar,
            )
            if use_surface and surface_support is not None:
                repair_valid &= ndimage.binary_dilation(surface_support | prior_mask | backbone, structure=ball_structure(max(repair_slice_close_radius, 1)))
                repair_valid |= backbone | sparse_seed
            pseudo = repair_connected_shape(
                pseudo,
                seed_mask=backbone | sparse_seed,
                valid_region=repair_valid,
                close_radius=repair_close_radius,
                slice_close_radius=repair_slice_close_radius,
                fill_holes=True,
            )
            if method in ("conn_surface_fill", "conn_surface_hu_fill") and int(pseudo.sum()) > int(1.25 * target_voxels):
                pseudo = connected_region_grow(
                    seed_mask=backbone | sparse_seed,
                    candidate_region=pseudo | backbone | sparse_seed,
                    cost=cost,
                    target_voxels=target_voxels,
                    max_cost=np.inf,
                )

    pseudo |= sparse_seed
    pseudo &= valid | sparse_seed
    pseudo = keep_seed_connected(pseudo, backbone | sparse_seed)
    pseudo |= sparse_seed
    return pseudo.astype(bool), backbone.astype(bool), cost.astype(np.float32), sparse_seed.astype(bool)
