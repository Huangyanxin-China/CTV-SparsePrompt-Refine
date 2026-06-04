#!/usr/bin/env python3
import argparse
import os
import sys

import numpy as np


def foreground_mean_dice(pred, target, num_classes):
    values = []
    for cls in range(1, num_classes):
        pred_c = pred == cls
        target_c = target == cls
        denom = pred_c.sum() + target_c.sum()
        if denom == 0:
            continue
        values.append(float(2.0 * (pred_c & target_c).sum() / denom))
    if not values:
        return np.nan
    return float(np.mean(values))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/share3/home/huangyanxin/DiffUNet-main")
    parser.add_argument("--train_dir", required=True)
    parser.add_argument("--logdir", required=True)
    parser.add_argument("--out_channels", type=int, required=True)
    parser.add_argument("--fold", type=int, default=0)
    parser.add_argument("--max_epoch", type=int, default=100)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--val_every", type=int, default=4)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--patch_size", nargs=3, type=int, default=[128, 128, 128])
    parser.add_argument("--steps_per_epoch", type=int, default=250)
    parser.add_argument("--val_number", type=int, default=50)
    parser.add_argument("--train_process", type=int, default=8)
    parser.add_argument("--master_port", type=int, default=17752)
    args = parser.parse_args()

    import torch
    import torch.nn as nn
    from monai.inferers import SlidingWindowInferer

    repo = os.path.abspath(args.repo)
    sys.path.insert(0, repo)

    from diffunet.diffunet_model import DiffUNet
    from light_training.dataloading.dataset import get_kfold_loader
    from light_training.trainer import Trainer
    from light_training.utils.files_helper import save_new_model_and_delete_last

    model_save_path = os.path.join(args.logdir, "model")
    os.makedirs(model_save_path, exist_ok=True)

    class DiffUNetTrainer(Trainer):
        def __init__(self):
            super().__init__(
                env_type="pytorch",
                max_epochs=args.max_epoch,
                batch_size=args.batch_size,
                device=args.device,
                val_every=args.val_every,
                num_gpus=1,
                logdir=args.logdir,
                master_port=args.master_port,
                training_script=__file__,
                train_process=args.train_process,
            )
            self.window_infer = SlidingWindowInferer(
                roi_size=args.patch_size,
                sw_batch_size=2,
                overlap=0.5,
                mode="gaussian",
            )
            self.patch_size = args.patch_size
            self.model = DiffUNet(1, args.out_channels)
            self.best_mean_dice = 0.0
            self.optimizer = torch.optim.SGD(
                self.model.parameters(),
                lr=1e-2,
                weight_decay=3e-5,
                momentum=0.99,
                nesterov=True,
            )
            self.scheduler_type = "poly"
            self.loss_func = nn.CrossEntropyLoss()
            self.num_step_per_epoch = args.steps_per_epoch
            self.val_number = args.val_number

        def get_input(self, batch):
            image = batch["data"]
            label = batch["seg"][:, 0].long()
            return image, label

        def training_step(self, batch):
            image, label = self.get_input(batch)
            pred = self.model(image, label)
            loss = self.loss_func(pred, label)
            self.log("training_loss", loss.mean(), step=self.global_step)
            return loss

        def validation_step(self, batch):
            image, label = self.get_input(batch)
            output = self.window_infer(image, self.model)
            output = output.argmax(dim=1)
            pred_np = output.detach().cpu().numpy()
            target_np = label.detach().cpu().numpy()
            scores = [
                foreground_mean_dice(pred_np[i], target_np[i], args.out_channels)
                for i in range(pred_np.shape[0])
            ]
            scores = [s for s in scores if not np.isnan(s)]
            if not scores:
                return torch.tensor(float("nan"))
            return torch.tensor(float(np.mean(scores)))

        def validation_end(self, val_outputs):
            if isinstance(val_outputs, list):
                val_outputs = torch.tensor(val_outputs)
            mean_dice = torch.nanmean(val_outputs.float()).item()
            print(f"mean foreground dice: {mean_dice:.4f}")
            self.log("mean_foreground_dice", mean_dice, step=self.epoch)
            if mean_dice > self.best_mean_dice:
                self.best_mean_dice = mean_dice
                save_new_model_and_delete_last(
                    self.model,
                    os.path.join(model_save_path, f"best_model_{mean_dice:.4f}.pt"),
                    delete_symbol="best_model",
                )
            save_new_model_and_delete_last(
                self.model,
                os.path.join(model_save_path, f"final_model_{mean_dice:.4f}.pt"),
                delete_symbol="final_model",
            )

    train_ds, val_ds, _ = get_kfold_loader(data_dir=args.train_dir, fold=args.fold)
    trainer = DiffUNetTrainer()
    trainer.train(train_dataset=train_ds, val_dataset=val_ds)


if __name__ == "__main__":
    main()
