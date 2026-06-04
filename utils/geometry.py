import numpy as np
from scipy import ndimage

try:
    import maxflow
except Exception:
    maxflow = None


def signed_distance(mask, sampling=None):
    mask = mask.astype(bool)
    if not mask.any():
        return np.full(mask.shape, -1e6, dtype=np.float32)
    inside = ndimage.distance_transform_edt(mask, sampling=sampling)
    outside = ndimage.distance_transform_edt(~mask, sampling=sampling)
    return (inside - outside).astype(np.float32)


def _validated_annotated_z(annotated_z, shape_z=None):
    annotated_z = np.sort(np.array(annotated_z, dtype=int))
    if annotated_z.size == 0:
        raise ValueError("annotated_z must contain at least one sparse prompt slice.")
    if shape_z is not None and (annotated_z[0] < 0 or annotated_z[-1] >= int(shape_z)):
        raise ValueError(f"annotated_z must be within [0, {int(shape_z) - 1}].")
    return annotated_z


def select_annotated_slices(mask3d, num_slices=3, mode="largest", seed=42):
    rng = np.random.default_rng(int(seed))
    z_indices = np.where(mask3d.reshape(mask3d.shape[0], -1).any(axis=1))[0]
    if len(z_indices) == 0:
        raise ValueError("Target mask is empty.")
    num_slices = int(num_slices)
    if num_slices <= 1:
        if mode == "random":
            return np.array([int(rng.choice(z_indices))], dtype=int)
        areas = mask3d[z_indices].reshape(len(z_indices), -1).sum(axis=1)
        return np.array([int(z_indices[int(np.argmax(areas))])], dtype=int)
    if mode == "random":
        return np.sort(rng.choice(z_indices, size=num_slices, replace=len(z_indices) < num_slices)).astype(int)
    if mode == "even":
        pos = np.linspace(0, len(z_indices) - 1, num_slices)
        return np.unique(z_indices[np.round(pos).astype(int)]).astype(int)

    areas = mask3d[z_indices].reshape(len(z_indices), -1).sum(axis=1)
    center = int(z_indices[int(np.argmax(areas))])
    candidates = [int(z_indices[0]), center, int(z_indices[-1])]
    if num_slices > 3:
        extra = rng.choice(z_indices, size=num_slices - 3, replace=len(z_indices) < num_slices - 3)
        candidates.extend([int(v) for v in extra])
    return np.sort(np.unique(candidates[:num_slices])).astype(int)


def sparse_sdf_propagation(mask3d, annotated_z, shrink_per_slice=1.0, max_z_distance=-1):
    annotated_z = _validated_annotated_z(annotated_z, shape_z=mask3d.shape[0])
    sdfs = {int(z): signed_distance(mask3d[int(z)]) for z in annotated_z}
    out = np.full(mask3d.shape, -1e6, dtype=np.float32)
    for z in range(mask3d.shape[0]):
        if z in sdfs:
            sdf = sdfs[z]
        elif z < annotated_z[0]:
            dist = int(annotated_z[0] - z)
            if max_z_distance >= 0 and dist > max_z_distance:
                continue
            sdf = sdfs[int(annotated_z[0])] - float(shrink_per_slice) * dist
        elif z > annotated_z[-1]:
            dist = int(z - annotated_z[-1])
            if max_z_distance >= 0 and dist > max_z_distance:
                continue
            sdf = sdfs[int(annotated_z[-1])] - float(shrink_per_slice) * dist
        else:
            right = int(np.searchsorted(annotated_z, z))
            z0 = int(annotated_z[right - 1])
            z1 = int(annotated_z[right])
            t = (z - z0) / max(z1 - z0, 1)
            sdf = (1.0 - t) * sdfs[z0] + t * sdfs[z1]
        out[z] = sdf.astype(np.float32)
    return out


def sparse_sdf_zcap_propagation(
    mask3d,
    annotated_z,
    mode="round",
    shrink_per_slice=1.0,
    plateau=4,
    cap_len=16,
    max_z_distance=25,
):
    """SDF propagation with non-linear end caps outside annotated z range.

    ``round`` keeps the nearest terminal contour for ``plateau`` slices, then
    closes it with a cosine shrink over ``cap_len`` slices. ``flat`` keeps the
    nearest terminal contour for ``plateau`` slices and then terminates it.
    Between annotated slices, the method uses the same SDF interpolation as the
    baseline, so this isolates endpoint-shape effects.
    """
    annotated_z = _validated_annotated_z(annotated_z, shape_z=mask3d.shape[0])
    sdfs = {int(z): signed_distance(mask3d[int(z)]) for z in annotated_z}
    out = np.full(mask3d.shape, -1e6, dtype=np.float32)
    plateau = max(int(plateau), 0)
    cap_len = max(int(cap_len), 1)
    max_z_distance = int(max_z_distance)
    mode = str(mode).lower()

    for z in range(mask3d.shape[0]):
        if z in sdfs:
            sdf = sdfs[z]
        elif annotated_z[0] < z < annotated_z[-1]:
            right = int(np.searchsorted(annotated_z, z))
            z0 = int(annotated_z[right - 1])
            z1 = int(annotated_z[right])
            t = (z - z0) / max(z1 - z0, 1)
            sdf = (1.0 - t) * sdfs[z0] + t * sdfs[z1]
        else:
            if z < annotated_z[0]:
                nearest = int(annotated_z[0])
                dist = int(nearest - z)
            else:
                nearest = int(annotated_z[-1])
                dist = int(z - nearest)
            if max_z_distance >= 0 and dist > max_z_distance:
                continue
            base = sdfs[nearest]
            if mode == "flat":
                if dist <= plateau:
                    sdf = base
                else:
                    continue
            elif mode == "round":
                if dist <= plateau:
                    shrink = 0.0
                elif dist <= plateau + cap_len:
                    t = (dist - plateau) / max(float(cap_len), 1.0)
                    close_amount = max(float(base.max()) + 1.0, float(shrink_per_slice) * cap_len)
                    shrink = close_amount * (1.0 - np.cos(np.pi * t)) / 2.0
                else:
                    continue
                sdf = base - float(shrink)
            else:
                sdf = base - float(shrink_per_slice) * dist
        out[z] = sdf.astype(np.float32)
    return out


def anatomy_valid_region(label, lung_label=1, avoid_labels=(2, 3, 4), lung_radius=12, exclude_lung=False):
    label = label.astype(np.int16)
    avoid = np.isin(label, np.array(avoid_labels, dtype=label.dtype))
    valid = ~avoid
    lung = label == int(lung_label)
    if lung.any() and int(lung_radius) >= 0:
        dist_to_lung = ndimage.distance_transform_edt(~lung)
        valid &= dist_to_lung <= float(lung_radius)
    if exclude_lung:
        valid &= ~lung
    return valid.astype(bool)


def local_max_skeleton_2d(mask2d):
    mask = mask2d.astype(bool)
    if not mask.any():
        return np.zeros(mask.shape, dtype=bool), np.zeros(mask.shape, dtype=np.float32)
    dist = ndimage.distance_transform_edt(mask)
    maxf = ndimage.maximum_filter(dist, size=3)
    skel = mask & (dist >= maxf) & (dist > 0)
    if not skel.any():
        coords = np.argwhere(mask)
        center = coords[len(coords) // 2]
        skel[tuple(center)] = True
    return skel.astype(bool), dist.astype(np.float32)


def skeleton_persistence(mask3d, annotated_z, persistence=6, min_radius=1.5, max_radius=5.0):
    shape = mask3d.shape
    thin = np.zeros(shape, dtype=bool)
    annotated_z = _validated_annotated_z(annotated_z, shape_z=shape[0])
    skels = {}
    radii = {}
    for z in annotated_z:
        skel, dist = local_max_skeleton_2d(mask3d[int(z)])
        skels[int(z)] = skel
        radius_vals = dist[skel]
        radius = float(np.median(radius_vals)) if radius_vals.size else float(min_radius)
        radii[int(z)] = float(np.clip(radius, min_radius, max_radius))

    yy, xx = np.ogrid[:shape[1], :shape[2]]
    for z in range(shape[0]):
        nearest = int(annotated_z[np.argmin(np.abs(annotated_z - z))])
        dz = abs(z - nearest)
        if dz > int(persistence):
            continue
        skel = skels[nearest]
        if not skel.any():
            continue
        radius = max(float(min_radius), radii[nearest] - 0.15 * dz)
        coords = np.argwhere(skel)
        slice_mask = np.zeros(shape[1:], dtype=bool)
        for y, x in coords:
            dist2 = (yy - int(y)) ** 2 + (xx - int(x)) ** 2
            slice_mask |= dist2 <= radius ** 2
        thin[z] = slice_mask
    return thin.astype(bool)


def organ_attachment_filter(mask, label, annotated_z, reference_mask, lung_label=1, tolerance=5.0):
    lung = label == int(lung_label)
    if not lung.any() or not mask.any():
        return mask.astype(bool)
    dist_to_lung = ndimage.distance_transform_edt(~lung)
    ref = np.zeros(mask.shape, dtype=bool)
    ref[np.array(annotated_z, dtype=int)] = reference_mask[np.array(annotated_z, dtype=int)].astype(bool)
    vals = dist_to_lung[ref]
    if vals.size == 0:
        return mask.astype(bool)
    center = float(np.median(vals))
    keep = np.abs(dist_to_lung - center) <= float(tolerance)
    return (mask.astype(bool) & keep).astype(bool)


def keep_seed_connected(mask, seed_mask):
    mask = mask.astype(bool)
    seed_mask = seed_mask.astype(bool)
    if not mask.any():
        return mask
    labeled, num = ndimage.label(mask)
    if num == 0:
        return mask
    ids = np.unique(labeled[seed_mask])
    ids = ids[ids > 0]
    if ids.size == 0:
        sizes = np.bincount(labeled.ravel())
        sizes[0] = 0
        return labeled == int(np.argmax(sizes))
    return np.isin(labeled, ids)


def z_uncertainty(shape, annotated_z, max_distance=24):
    z = np.arange(shape[0], dtype=np.float32)
    annotated_z = _validated_annotated_z(annotated_z, shape_z=shape[0]).astype(np.float32)
    d = np.min(np.abs(z[:, None] - annotated_z[None, :]), axis=1)
    d = np.clip(d, 0, float(max_distance)) / max(float(max_distance), 1.0)
    return d[:, None, None].repeat(shape[1], axis=1).repeat(shape[2], axis=2).astype(np.float32)


def sparse_geodesic_probability(
    image,
    label,
    target_mask,
    annotated_z,
    valid_region=None,
    iterations=96,
    hu_sigma=80.0,
    grad_sigma=1.0,
    z_weight=0.03,
    shape_weight=0.20,
    neighbor_weight=0.80,
    oar_penalty=2.0,
    threshold=0.5,
):
    """Diffuse sparse foreground seeds through low image/anatomy cost regions.

    This is a graph/geodesic-like label propagation approximation. It does not
    interpolate SDF values directly; foreground probability is iteratively
    propagated through 6-neighborhood edges weighted by image cost, z-distance,
    anatomy validity, and a weak shape prior.
    """
    image = image.astype(np.float32)
    target_mask = target_mask.astype(bool)
    annotated_z = _validated_annotated_z(annotated_z, shape_z=target_mask.shape[0])
    seed = np.zeros(target_mask.shape, dtype=bool)
    known = np.zeros(target_mask.shape, dtype=bool)
    seed[annotated_z] = target_mask[annotated_z]
    known[annotated_z] = True

    if valid_region is None:
        valid_region = np.ones(target_mask.shape, dtype=bool)
    valid_region = valid_region.astype(bool)

    seed_values = image[seed]
    hu_center = float(np.median(seed_values)) if seed_values.size else float(np.median(image))
    hu_cost = np.abs(image - hu_center) / max(float(hu_sigma), 1.0)

    smoothed = ndimage.gaussian_filter(image, sigma=max(float(grad_sigma), 0.0))
    grad = np.sqrt(sum(g ** 2 for g in np.gradient(smoothed))).astype(np.float32)
    p95 = float(np.percentile(grad, 95))
    if p95 > 1e-6:
        grad = np.clip(grad / p95, 0.0, 3.0)

    z_cost = z_uncertainty(target_mask.shape, annotated_z, max_distance=max(target_mask.shape[0], 1))
    cost = hu_cost + grad + float(z_weight) * z_cost
    cost += (~valid_region).astype(np.float32) * float(oar_penalty)
    conductance = np.exp(-cost).astype(np.float32)
    conductance *= valid_region.astype(np.float32)

    shape_sdf = sparse_sdf_propagation(target_mask, annotated_z, shrink_per_slice=1.0, max_z_distance=-1)
    shape_prob = 1.0 / (1.0 + np.exp(-np.clip(shape_sdf / 4.0, -20.0, 20.0)))
    prob = shape_prob.astype(np.float32) * 0.25
    prob[seed] = 1.0
    prob[known & (~seed)] = 0.0
    prob[~valid_region] = 0.0

    for _ in range(int(iterations)):
        acc = np.zeros_like(prob, dtype=np.float32)
        wsum = np.zeros_like(prob, dtype=np.float32)
        for axis in range(3):
            src = [slice(None)] * 3
            dst = [slice(None)] * 3
            src[axis] = slice(1, None)
            dst[axis] = slice(0, -1)
            src = tuple(src)
            dst = tuple(dst)
            w = np.sqrt(conductance[src] * conductance[dst]).astype(np.float32)
            acc[dst] += w * prob[src]
            wsum[dst] += w
            acc[src] += w * prob[dst]
            wsum[src] += w
        neighbor = acc / np.maximum(wsum, 1e-6)
        prob = float(neighbor_weight) * neighbor + float(shape_weight) * shape_prob
        prob[seed] = 1.0
        prob[known & (~seed)] = 0.0
        prob[~valid_region] = 0.0

    pseudo = prob >= float(threshold)
    pseudo[annotated_z] = target_mask[annotated_z]
    return pseudo.astype(bool), prob.astype(np.float32)


def graphcut_like_refine(
    image,
    label,
    prior_mask,
    sparse_seed,
    valid_region=None,
    iterations=64,
    hu_sigma=80.0,
    shape_weight=0.45,
    neighbor_weight=0.55,
    threshold=0.5,
):
    """Refine a prior by edge-aware probability smoothing with fixed sparse seeds."""
    prior_mask = prior_mask.astype(bool)
    sparse_seed = sparse_seed.astype(bool)
    if valid_region is None:
        valid_region = np.ones(prior_mask.shape, dtype=bool)
    valid_region = valid_region.astype(bool)

    vals = image.astype(np.float32)[sparse_seed]
    center = float(np.median(vals)) if vals.size else float(np.median(image))
    hu_cost = np.abs(image.astype(np.float32) - center) / max(float(hu_sigma), 1.0)
    grad = np.sqrt(sum(g ** 2 for g in np.gradient(ndimage.gaussian_filter(image.astype(np.float32), 1.0)))).astype(np.float32)
    p95 = float(np.percentile(grad, 95))
    if p95 > 1e-6:
        grad = np.clip(grad / p95, 0.0, 3.0)
    conductance = np.exp(-(hu_cost + grad)).astype(np.float32) * valid_region.astype(np.float32)

    shape_prob = 1.0 / (1.0 + np.exp(-np.clip(signed_distance(prior_mask) / 3.0, -20.0, 20.0)))
    prob = shape_prob.astype(np.float32)
    prob[sparse_seed] = 1.0
    prob[~valid_region] = 0.0

    for _ in range(int(iterations)):
        acc = np.zeros_like(prob, dtype=np.float32)
        wsum = np.zeros_like(prob, dtype=np.float32)
        for axis in range(3):
            src = [slice(None)] * 3
            dst = [slice(None)] * 3
            src[axis] = slice(1, None)
            dst[axis] = slice(0, -1)
            src = tuple(src)
            dst = tuple(dst)
            w = np.sqrt(conductance[src] * conductance[dst]).astype(np.float32)
            acc[dst] += w * prob[src]
            wsum[dst] += w
            acc[src] += w * prob[dst]
            wsum[src] += w
        neighbor = acc / np.maximum(wsum, 1e-6)
        prob = float(neighbor_weight) * neighbor + float(shape_weight) * shape_prob
        prob[sparse_seed] = 1.0
        prob[~valid_region] = 0.0

    return (prob >= float(threshold)).astype(bool), prob.astype(np.float32)


def binary_boundary(mask, structure=None):
    mask = mask.astype(bool)
    if structure is None:
        structure = ndimage.generate_binary_structure(mask.ndim, 1)
    if not mask.any():
        return np.zeros(mask.shape, dtype=bool)
    eroded = ndimage.binary_erosion(mask, structure=structure, border_value=0)
    return mask & (~eroded)


def _slice_contact_stats(mask2d, organ2d, contact_radius=5.0, min_sigma=1.5):
    boundary = binary_boundary(mask2d, structure=np.ones((3, 3), dtype=bool))
    if not boundary.any() or not organ2d.any():
        return 0.0, float(contact_radius), float(max(min_sigma, contact_radius / 2.0))
    dist = ndimage.distance_transform_edt(~organ2d.astype(bool))
    vals = dist[boundary]
    if vals.size == 0:
        return 0.0, float(contact_radius), float(max(min_sigma, contact_radius / 2.0))
    contact_vals = vals[vals <= float(contact_radius)]
    ratio = float(contact_vals.size) / float(vals.size)
    use_vals = contact_vals if contact_vals.size > 0 else vals
    mu = float(np.median(use_vals))
    sigma = float(np.std(use_vals))
    sigma = max(float(min_sigma), sigma)
    return ratio, mu, sigma


def sparse_contact_profiles(
    label,
    target_mask,
    annotated_z,
    organ_labels=(1, 2, 3, 4),
    contact_radius=5.0,
    min_sigma=1.5,
    mode="z",
):
    """Estimate case-specific CTV-organ distance profiles from sparse slices.

    The returned per-z arrays are intentionally simple: for each organ label,
    alpha is the boundary-contact ratio, mu/sigma describe CTV-boundary distance
    to that organ. ``mode='global'`` repeats one global profile over z; ``mode='z'``
    linearly interpolates profiles between annotated slices.
    """
    annotated_z = _validated_annotated_z(annotated_z, shape_z=label.shape[0])
    z_all = np.arange(label.shape[0], dtype=np.float32)
    profiles = {}
    for organ_label in organ_labels:
        alpha_vals = []
        mu_vals = []
        sigma_vals = []
        for z in annotated_z:
            ratio, mu, sigma = _slice_contact_stats(
                target_mask[int(z)],
                label[int(z)] == int(organ_label),
                contact_radius=contact_radius,
                min_sigma=min_sigma,
            )
            alpha_vals.append(ratio)
            mu_vals.append(mu)
            sigma_vals.append(sigma)
        alpha_vals = np.asarray(alpha_vals, dtype=np.float32)
        mu_vals = np.asarray(mu_vals, dtype=np.float32)
        sigma_vals = np.asarray(sigma_vals, dtype=np.float32)
        if mode == "global" or len(annotated_z) == 1:
            alpha = np.full(label.shape[0], float(np.mean(alpha_vals)), dtype=np.float32)
            mu = np.full(label.shape[0], float(np.mean(mu_vals)), dtype=np.float32)
            sigma = np.full(label.shape[0], float(np.mean(sigma_vals)), dtype=np.float32)
        else:
            alpha = np.interp(z_all, annotated_z.astype(np.float32), alpha_vals).astype(np.float32)
            mu = np.interp(z_all, annotated_z.astype(np.float32), mu_vals).astype(np.float32)
            sigma = np.interp(z_all, annotated_z.astype(np.float32), sigma_vals).astype(np.float32)
        profiles[int(organ_label)] = {"alpha": alpha, "mu": mu, "sigma": np.maximum(sigma, float(min_sigma))}
    return profiles


def contact_likelihood_volume(
    label,
    target_mask,
    annotated_z,
    organ_labels=(1, 2, 3, 4),
    contact_radius=5.0,
    min_sigma=1.5,
    mode="z",
):
    profiles = sparse_contact_profiles(
        label=label,
        target_mask=target_mask,
        annotated_z=annotated_z,
        organ_labels=organ_labels,
        contact_radius=contact_radius,
        min_sigma=min_sigma,
        mode=mode,
    )
    like = np.zeros(label.shape, dtype=np.float32)
    weight_sum = np.zeros(label.shape, dtype=np.float32)
    for organ_label, prof in profiles.items():
        organ = label == int(organ_label)
        if not organ.any():
            continue
        dist = ndimage.distance_transform_edt(~organ).astype(np.float32)
        alpha = prof["alpha"][:, None, None].astype(np.float32)
        mu = prof["mu"][:, None, None].astype(np.float32)
        sigma = prof["sigma"][:, None, None].astype(np.float32)
        term = np.exp(-((dist - mu) ** 2) / (2.0 * np.maximum(sigma, 1e-3) ** 2)).astype(np.float32)
        like += alpha * term
        weight_sum += alpha
    like = like / np.maximum(weight_sum, 1e-6)
    return np.clip(like, 0.0, 1.0).astype(np.float32), profiles


def sparse_hu_likelihood(image, target_mask, annotated_z, min_sigma=40.0):
    seed = np.zeros(target_mask.shape, dtype=bool)
    seed[np.array(annotated_z, dtype=int)] = target_mask[np.array(annotated_z, dtype=int)]
    vals = image.astype(np.float32)[seed]
    if vals.size == 0:
        return np.ones(target_mask.shape, dtype=np.float32) * 0.5
    center = float(np.median(vals))
    mad = float(np.median(np.abs(vals - center))) if vals.size else 0.0
    sigma = max(float(min_sigma), 1.4826 * mad)
    like = np.exp(-((image.astype(np.float32) - center) ** 2) / (2.0 * sigma ** 2))
    return np.clip(like, 0.0, 1.0).astype(np.float32)


def corridor_likelihood_volume(
    image,
    label,
    target_mask,
    annotated_z,
    lung_label=1,
    oar_labels=(2, 3, 4),
    lung_band=8.0,
    oar_band=5.0,
    hu_min_sigma=40.0,
):
    lung = label == int(lung_label)
    oar = np.isin(label.astype(np.int16), np.array(oar_labels, dtype=np.int16))
    if not lung.any() or not oar.any():
        return np.zeros(label.shape, dtype=np.float32)
    d_lung = ndimage.distance_transform_edt(~lung).astype(np.float32)
    d_oar = ndimage.distance_transform_edt(~oar).astype(np.float32)
    lung_like = np.exp(-(d_lung ** 2) / (2.0 * max(float(lung_band), 1e-3) ** 2))
    oar_like = np.exp(-(d_oar ** 2) / (2.0 * max(float(oar_band), 1e-3) ** 2))
    hu_like = sparse_hu_likelihood(image, target_mask, annotated_z, min_sigma=hu_min_sigma)
    corridor = lung_like * oar_like * hu_like
    corridor[oar] *= 0.25
    return np.clip(corridor, 0.0, 1.0).astype(np.float32)


def _bbox_slices(mask, margin=2):
    coords = np.argwhere(mask)
    if coords.size == 0:
        return tuple(slice(0, s) for s in mask.shape)
    start = np.maximum(coords.min(axis=0) - int(margin), 0)
    stop = np.minimum(coords.max(axis=0) + int(margin) + 1, np.array(mask.shape))
    return tuple(slice(int(a), int(b)) for a, b in zip(start, stop))


def _maxflow_binary_refine(
    unary_prob,
    conductance,
    prior_mask,
    target_mask,
    annotated_z,
    valid_region,
    free_region,
    pairwise_weight=0.55,
):
    if maxflow is None:
        raise RuntimeError("PyMaxflow is not available. Install PyMaxflow or use solver='iterative'.")

    prior_mask = prior_mask.astype(bool)
    target_mask = target_mask.astype(bool)
    valid_region = valid_region.astype(bool)
    free_region = free_region.astype(bool)
    annotated_z = _validated_annotated_z(annotated_z, shape_z=prior_mask.shape[0])

    known = np.zeros(prior_mask.shape, dtype=bool)
    known[annotated_z] = True
    known_fg = known & target_mask
    known_bg = known & (~target_mask)

    crop_mask = prior_mask | free_region | known_fg
    if not crop_mask.any():
        out = np.zeros(prior_mask.shape, dtype=bool)
        out[annotated_z] = target_mask[annotated_z]
        return out, out.astype(np.float32)

    slc = _bbox_slices(crop_mask, margin=2)
    p = np.clip(unary_prob[slc].astype(np.float64), 1e-5, 1.0 - 1e-5)
    prior_c = prior_mask[slc]
    valid_c = valid_region[slc]
    free_c = free_region[slc]
    known_fg_c = known_fg[slc]
    known_bg_c = known_bg[slc]

    d_fg = -np.log(p)
    d_bg = -np.log(1.0 - p)
    source_caps = d_bg.copy()
    sink_caps = d_fg.copy()

    big = 1e6
    fixed = ~free_c
    fixed_fg = fixed & prior_c & valid_c
    fixed_bg = fixed & (~prior_c)

    # PyMaxflow convention: source segment cost is sink_cap, sink segment cost is source_cap.
    source_caps[fixed_fg] = big
    sink_caps[fixed_fg] = 0.0
    source_caps[fixed_bg] = 0.0
    sink_caps[fixed_bg] = big
    source_caps[~valid_c] = 0.0
    sink_caps[~valid_c] = big
    source_caps[known_fg_c] = big
    sink_caps[known_fg_c] = 0.0
    source_caps[known_bg_c] = 0.0
    sink_caps[known_bg_c] = big

    g = maxflow.Graph[float]()
    nodeids = g.add_grid_nodes(p.shape)
    g.add_grid_tedges(nodeids, source_caps, sink_caps)

    edge_weights = np.clip(conductance[slc].astype(np.float64), 0.0, 1.0) * float(pairwise_weight)
    structure = maxflow.vonNeumann_structure(ndim=3, directed=True)
    g.add_grid_edges(nodeids, weights=edge_weights, structure=structure, symmetric=True)
    g.maxflow()
    segments = g.get_grid_segments(nodeids)
    pred_c = ~segments

    out = prior_mask & valid_region
    out[slc] = pred_c
    out[annotated_z] = target_mask[annotated_z]
    out[~valid_region] = False
    return out.astype(bool), out.astype(np.float32)


def graphcut_contact_refine(
    image,
    label,
    prior_mask,
    target_mask,
    annotated_z,
    valid_region=None,
    use_lung_prior=False,
    use_contact_prior=False,
    contact_mode="z",
    iterations=80,
    hu_sigma=80.0,
    grad_sigma=1.0,
    sdf_tau=4.0,
    unary_weight=0.45,
    neighbor_weight=0.55,
    contact_weight=0.35,
    lung_weight=0.20,
    use_hu_prior=False,
    hu_weight=0.20,
    use_corridor_prior=False,
    corridor_weight=0.25,
    corridor_lung_band=8.0,
    corridor_oar_band=5.0,
    use_soft_oar=False,
    soft_oar_margin=3.0,
    soft_oar_weight=0.75,
    contact_radius=5.0,
    contact_min_sigma=1.5,
    contact_band=12.0,
    lung_radius=12.0,
    threshold=0.5,
    solver="auto",
):
    """Graph-cut energy refinement with case-specific organ-contact prior."""
    image = image.astype(np.float32)
    prior_mask = prior_mask.astype(bool)
    target_mask = target_mask.astype(bool)
    annotated_z = _validated_annotated_z(annotated_z, shape_z=prior_mask.shape[0])
    if valid_region is None:
        valid_region = np.ones(prior_mask.shape, dtype=bool)
    valid_region = valid_region.astype(bool)

    known = np.zeros(prior_mask.shape, dtype=bool)
    known[annotated_z] = True
    known_fg = known & target_mask
    known_bg = known & (~target_mask)

    prior_sdf = signed_distance(prior_mask)
    shape_prob = 1.0 / (1.0 + np.exp(-np.clip(prior_sdf / max(float(sdf_tau), 1e-3), -20.0, 20.0)))
    unary = shape_prob.astype(np.float32)
    total_weight = 1.0

    if use_lung_prior:
        lung = label == 1
        if lung.any():
            d_lung = ndimage.distance_transform_edt(~lung).astype(np.float32)
            lung_prob = np.exp(-(d_lung ** 2) / (2.0 * max(float(lung_radius), 1e-3) ** 2)).astype(np.float32)
            unary += float(lung_weight) * lung_prob
            total_weight += float(lung_weight)

    if use_hu_prior:
        hu_like = sparse_hu_likelihood(image, target_mask, annotated_z)
        if float(contact_band) > 0:
            hu_like = hu_like * (np.abs(prior_sdf) <= float(contact_band)).astype(np.float32)
        unary += float(hu_weight) * hu_like
        total_weight += float(hu_weight)

    if use_corridor_prior:
        corridor = corridor_likelihood_volume(
            image=image,
            label=label,
            target_mask=target_mask,
            annotated_z=annotated_z,
            lung_band=corridor_lung_band,
            oar_band=corridor_oar_band,
        )
        if float(contact_band) > 0:
            corridor = corridor * (np.abs(prior_sdf) <= float(contact_band)).astype(np.float32)
        unary += float(corridor_weight) * corridor
        total_weight += float(corridor_weight)

    if use_contact_prior:
        contact_like, _ = contact_likelihood_volume(
            label=label,
            target_mask=target_mask,
            annotated_z=annotated_z,
            organ_labels=(1, 2, 3, 4),
            contact_radius=contact_radius,
            min_sigma=contact_min_sigma,
            mode=contact_mode,
        )
        if float(contact_band) > 0:
            band = np.abs(prior_sdf) <= float(contact_band)
            contact_like = contact_like * band.astype(np.float32)
        unary += float(contact_weight) * contact_like
        total_weight += float(contact_weight)

    unary = np.clip(unary / max(total_weight, 1e-6), 0.0, 1.0).astype(np.float32)

    if use_soft_oar:
        oar = (label == 2) | (label == 3) | (label == 4)
        if oar.any():
            inside = ndimage.distance_transform_edt(oar).astype(np.float32)
            suppress = np.zeros_like(unary, dtype=np.float32)
            if float(soft_oar_margin) <= 0:
                suppress[oar] = 1.0
            else:
                suppress[oar] = np.clip(inside[oar] / float(soft_oar_margin), 0.0, 1.0)
            unary *= (1.0 - float(soft_oar_weight) * suppress)
            unary = np.clip(unary, 1e-5, 1.0 - 1e-5)

    vals = image[known_fg]
    center = float(np.median(vals)) if vals.size else float(np.median(image))
    hu_cost = np.abs(image - center) / max(float(hu_sigma), 1.0)
    smoothed = ndimage.gaussian_filter(image, sigma=max(float(grad_sigma), 0.0))
    grad = np.sqrt(sum(g ** 2 for g in np.gradient(smoothed))).astype(np.float32)
    p95 = float(np.percentile(grad, 95))
    if p95 > 1e-6:
        grad = np.clip(grad / p95, 0.0, 3.0)
    conductance = np.exp(-(hu_cost + grad)).astype(np.float32) * valid_region.astype(np.float32)

    free_band_width = max(float(contact_band), 12.0)
    free_region = (np.abs(prior_sdf) <= free_band_width) & valid_region
    free_region |= known_fg

    if solver == "auto":
        solver = "maxflow" if maxflow is not None else "iterative"
    if solver == "maxflow":
        return _maxflow_binary_refine(
            unary_prob=unary,
            conductance=conductance,
            prior_mask=prior_mask,
            target_mask=target_mask,
            annotated_z=annotated_z,
            valid_region=valid_region,
            free_region=free_region,
            pairwise_weight=neighbor_weight,
        )
    if solver != "iterative":
        raise ValueError(f"Unknown graphcut solver: {solver}")

    prob = unary.copy()
    prob[known_fg] = 1.0
    prob[known_bg] = 0.0
    prob[~valid_region] = 0.0

    for _ in range(int(iterations)):
        acc = np.zeros_like(prob, dtype=np.float32)
        wsum = np.zeros_like(prob, dtype=np.float32)
        for axis in range(3):
            src = [slice(None)] * 3
            dst = [slice(None)] * 3
            src[axis] = slice(1, None)
            dst[axis] = slice(0, -1)
            src = tuple(src)
            dst = tuple(dst)
            w = np.sqrt(conductance[src] * conductance[dst]).astype(np.float32)
            acc[dst] += w * prob[src]
            wsum[dst] += w
            acc[src] += w * prob[dst]
            wsum[src] += w
        neighbor = acc / np.maximum(wsum, 1e-6)
        prob = float(neighbor_weight) * neighbor + float(unary_weight) * unary
        prob = np.clip(prob / max(float(neighbor_weight) + float(unary_weight), 1e-6), 0.0, 1.0)
        prob[known_fg] = 1.0
        prob[known_bg] = 0.0
        prob[~valid_region] = 0.0

    return (prob >= float(threshold)).astype(bool), prob.astype(np.float32)
