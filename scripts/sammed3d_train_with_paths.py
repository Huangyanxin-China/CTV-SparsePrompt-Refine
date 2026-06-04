#!/usr/bin/env python3
import argparse
import os
import runpy
import sys
import types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/share3/home/huangyanxin/SAM-Med3D-main")
    parser.add_argument("--data_paths", nargs="+", required=True)
    parser.add_argument("--task_name", required=True)
    parser.add_argument("--work_dir", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--gpu_ids", nargs="+", type=int, default=[0])
    parser.add_argument("--multi_gpu", action="store_true")
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--num_workers", type=int, default=4)
    parser.add_argument("--num_epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--weight_decay", type=float, default=0.05)
    parser.add_argument("--accumulation_steps", type=int, default=4)
    parser.add_argument("--img_size", type=int, default=128)
    parser.add_argument("--port", type=int, default=12361)
    parser.add_argument("--allow_partial_weight", action="store_true")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    train_py = os.path.join(repo, "train.py")
    if not os.path.exists(train_py):
        raise FileNotFoundError(train_py)

    abs_data_paths = [os.path.abspath(p) for p in args.data_paths]
    for path in abs_data_paths:
        if not os.path.isdir(path):
            raise FileNotFoundError(path)

    sys.path.insert(0, repo)
    os.chdir(repo)

    data_paths_module = types.ModuleType("utils.data_paths")
    data_paths_module.img_datas = abs_data_paths
    sys.modules["utils.data_paths"] = data_paths_module

    argv = [
        train_py,
        "--task_name", args.task_name,
        "--work_dir", os.path.abspath(args.work_dir),
        "--checkpoint", os.path.abspath(args.checkpoint),
        "--batch_size", str(args.batch_size),
        "--num_workers", str(args.num_workers),
        "--num_epochs", str(args.num_epochs),
        "--lr", str(args.lr),
        "--weight_decay", str(args.weight_decay),
        "--accumulation_steps", str(args.accumulation_steps),
        "--img_size", str(args.img_size),
        "--port", str(args.port),
        "--gpu_ids", *[str(g) for g in args.gpu_ids],
        "--multi_click",
    ]
    if args.multi_gpu:
        argv.append("--multi_gpu")
    if args.allow_partial_weight:
        argv.append("--allow_partial_weight")

    print("SAM-Med3D data paths:", abs_data_paths)
    print("Executing:", " ".join(argv))
    sys.argv = argv
    runpy.run_path(train_py, run_name="__main__")


if __name__ == "__main__":
    main()
