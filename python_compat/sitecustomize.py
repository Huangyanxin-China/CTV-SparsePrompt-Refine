try:
    import torch

    if not hasattr(torch, "GradScaler"):
        from torch.cuda.amp import GradScaler as _CudaAmpGradScaler

        def _compat_grad_scaler(device="cuda", *args, **kwargs):
            if args and not isinstance(device, str):
                return _CudaAmpGradScaler(device, *args, **kwargs)
            return _CudaAmpGradScaler(*args, **kwargs)

        torch.GradScaler = _compat_grad_scaler
except Exception:
    pass
