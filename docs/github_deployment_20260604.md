# GitHub Deployment Notes

This project is ready for public GitHub upload after the cleanup audit. The
server currently does not have GitHub write credentials configured, so the
actual repository creation and push require a GitHub token or SSH key from the
account owner.

## Prepared local state

- Local branch: `main`
- Initial commit: `3b1eb96`
- Project remote URL:
  `https://github.com/Huangyanxin-China/CTV-SparsePrompt-Refine.git`
- Static showcase page:
  `site/index.html`
- User-page target path:
  `https://Huangyanxin-China.github.io/ctv-sparse-prompt-refine/`

The public Git payload excludes private clinical CT, DICOM, NIfTI masks,
nnUNet caches, model checkpoints, prediction volumes, logs, and large result
directories through `.gitignore`.

## One-command deployment after GitHub token setup

Create a GitHub personal access token with repository write permission, then
run:

```bash
cd /share3/home/huangyanxin/CTV_SparsePrompt_Refine
export GITHUB_TOKEN='YOUR_TOKEN_HERE'
bash scripts/deploy_to_github_pages.sh
unset GITHUB_TOKEN
```

The script will:

1. Create `Huangyanxin-China/CTV-SparsePrompt-Refine` if it does not exist.
2. Push the current `main` branch to that repository.
3. Create `Huangyanxin-China/Huangyanxin-China.github.io` if it does not exist.
4. Copy `site/` into the user-page repository at
   `ctv-sparse-prompt-refine/`.
5. Add a link from the user-page root `index.html` when possible.

## Manual fallback

If you prefer manual Git commands:

```bash
cd /share3/home/huangyanxin/CTV_SparsePrompt_Refine
git remote set-url origin https://github.com/Huangyanxin-China/CTV-SparsePrompt-Refine.git
git push -u origin main
```

For the user page:

```bash
git clone https://github.com/Huangyanxin-China/Huangyanxin-China.github.io.git
cd Huangyanxin-China.github.io
mkdir -p ctv-sparse-prompt-refine
rsync -a --delete /share3/home/huangyanxin/CTV_SparsePrompt_Refine/site/ ctv-sparse-prompt-refine/
git add .
git commit -m "Add CTV sparse-prompt refinement showcase"
git push
```
