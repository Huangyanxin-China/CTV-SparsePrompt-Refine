#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OWNER="${GITHUB_OWNER:-Huangyanxin-China}"
PROJECT_REPO="${PROJECT_REPO:-CTV-SparsePrompt-Refine}"
USER_PAGE_REPO="${USER_PAGE_REPO:-${OWNER}.github.io}"
PROJECT_BRANCH="${PROJECT_BRANCH:-main}"
PROJECT_DESCRIPTION="${PROJECT_DESCRIPTION:-Sparse-prompt CTV completion and pseudo-to-true refinement workflow.}"
SHOWCASE_PATH="${SHOWCASE_PATH:-ctv-sparse-prompt-refine}"
VISIBILITY="${GITHUB_REPO_VISIBILITY:-public}"
API_ROOT="https://api.github.com"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "ERROR: GITHUB_TOKEN is not set." >&2
    echo "Create a GitHub token with repo scope, then run:" >&2
    echo "  export GITHUB_TOKEN='...'" >&2
    exit 2
fi

if [[ "${VISIBILITY}" != "public" && "${VISIBILITY}" != "private" ]]; then
    echo "ERROR: GITHUB_REPO_VISIBILITY must be public or private." >&2
    exit 2
fi

repo_http_code() {
    local repo_name="$1"
    curl -sS -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        "${API_ROOT}/repos/${OWNER}/${repo_name}"
}

create_repo_if_needed() {
    local repo_name="$1"
    local description="$2"
    local code
    code="$(repo_http_code "${repo_name}")"
    case "${code}" in
        200)
            echo "Repository exists: ${OWNER}/${repo_name}"
            ;;
        404)
            echo "Creating repository: ${OWNER}/${repo_name}"
            local private_flag="false"
            if [[ "${VISIBILITY}" == "private" ]]; then
                private_flag="true"
            fi
            python - "${repo_name}" "${description}" "${private_flag}" <<'PY' > /tmp/github_repo_payload.json
import json
import sys
name, description, private_flag = sys.argv[1], sys.argv[2], sys.argv[3] == "true"
print(json.dumps({
    "name": name,
    "description": description,
    "private": private_flag,
    "auto_init": False,
    "has_issues": True,
    "has_projects": False,
    "has_wiki": False,
}))
PY
            curl -fsS \
                -X POST \
                -H "Authorization: Bearer ${GITHUB_TOKEN}" \
                -H "Accept: application/vnd.github+json" \
                "${API_ROOT}/user/repos" \
                --data @/tmp/github_repo_payload.json >/dev/null
            rm -f /tmp/github_repo_payload.json
            ;;
        *)
            echo "ERROR: cannot inspect ${OWNER}/${repo_name}; GitHub API HTTP ${code}" >&2
            exit 1
            ;;
    esac
}

make_askpass() {
    local askpass
    askpass="$(mktemp)"
    cat > "${askpass}" <<'SH'
#!/usr/bin/env bash
case "$1" in
    *Username*) printf '%s\n' "x-access-token" ;;
    *Password*) printf '%s\n' "${GITHUB_TOKEN}" ;;
    *) printf '\n' ;;
esac
SH
    chmod 700 "${askpass}"
    printf '%s\n' "${askpass}"
}

push_project_repo() {
    echo "Pushing project repository..."
    cd "${PROJECT_ROOT}"
    git remote add origin "https://github.com/${OWNER}/${PROJECT_REPO}.git" 2>/dev/null || \
        git remote set-url origin "https://github.com/${OWNER}/${PROJECT_REPO}.git"
    local askpass
    askpass="$(make_askpass)"
    GIT_ASKPASS="${askpass}" GIT_TERMINAL_PROMPT=0 git push -u origin "${PROJECT_BRANCH}"
    rm -f "${askpass}"
}

write_default_user_page_index() {
    local index_file="$1"
    cat > "${index_file}" <<HTML
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${OWNER}</title>
  <style>
    body { margin: 0; font-family: Arial, Helvetica, sans-serif; color: #1f2933; background: #ffffff; line-height: 1.55; }
    main { width: min(960px, calc(100% - 36px)); margin: 0 auto; padding: 48px 0; }
    h1 { margin: 0 0 12px; font-size: 40px; letter-spacing: 0; }
    a { color: #0a7f6a; font-weight: 700; }
    .project { border-top: 1px solid #d8dee7; padding-top: 22px; margin-top: 28px; }
  </style>
</head>
<body>
  <main>
    <h1>${OWNER}</h1>
    <p>Research projects and reproducible materials.</p>
    <section class="project">
      <h2>CTV Sparse-Prompt Refinement</h2>
      <p>Sparse-prompt CTV completion with SDF core-envelope preprocessing and constrained pseudo-to-true refinement.</p>
      <p><a href="./${SHOWCASE_PATH}/">Open project showcase</a></p>
    </section>
  </main>
</body>
</html>
HTML
}

insert_user_page_link_if_possible() {
    local index_file="$1"
    if [[ ! -f "${index_file}" ]]; then
        write_default_user_page_index "${index_file}"
        return
    fi
    if grep -q "${SHOWCASE_PATH}" "${index_file}"; then
        echo "User page index already links to ${SHOWCASE_PATH}"
        return
    fi
    python - "${index_file}" "${SHOWCASE_PATH}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
showcase = sys.argv[2]
text = path.read_text(encoding="utf-8", errors="ignore")
snippet = f"""
<!-- CTV sparse-prompt showcase link inserted by deploy_to_github_pages.sh -->
<section class="project">
  <h2>CTV Sparse-Prompt Refinement</h2>
  <p>Sparse-prompt CTV completion with SDF core-envelope preprocessing and constrained pseudo-to-true refinement.</p>
  <p><a href="./{showcase}/">Open project showcase</a></p>
</section>
"""
if "</main>" in text:
    text = text.replace("</main>", snippet + "\n</main>", 1)
elif "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
else:
    text += "\n" + snippet
path.write_text(text, encoding="utf-8")
PY
}

update_user_page_repo() {
    echo "Updating user page repository..."
    local workdir askpass
    workdir="$(mktemp -d)"
    askpass="$(make_askpass)"
    GIT_ASKPASS="${askpass}" GIT_TERMINAL_PROMPT=0 \
        git clone "https://github.com/${OWNER}/${USER_PAGE_REPO}.git" "${workdir}/${USER_PAGE_REPO}"
    rm -f "${askpass}"

    mkdir -p "${workdir}/${USER_PAGE_REPO}/${SHOWCASE_PATH}"
    rsync -a --delete "${PROJECT_ROOT}/site/" "${workdir}/${USER_PAGE_REPO}/${SHOWCASE_PATH}/"
    insert_user_page_link_if_possible "${workdir}/${USER_PAGE_REPO}/index.html"

    cd "${workdir}/${USER_PAGE_REPO}"
    git config user.name "${OWNER}"
    git config user.email "${OWNER}@users.noreply.github.com"
    git add .
    if git diff --cached --quiet; then
        echo "No user page changes to commit."
    else
        git commit -m "Add CTV sparse-prompt refinement showcase"
        askpass="$(make_askpass)"
        GIT_ASKPASS="${askpass}" GIT_TERMINAL_PROMPT=0 git push origin HEAD
        rm -f "${askpass}"
    fi
    rm -rf "${workdir}"
}

enable_project_pages_hint() {
    cat <<EOF

Project repository pushed:
  https://github.com/${OWNER}/${PROJECT_REPO}

User page showcase path:
  https://${OWNER}.github.io/${SHOWCASE_PATH}/

If the project repository should also have GitHub Pages, enable Pages in:
  https://github.com/${OWNER}/${PROJECT_REPO}/settings/pages
and use the /site directory or GitHub Actions to publish it.
EOF
}

cd "${PROJECT_ROOT}"
create_repo_if_needed "${PROJECT_REPO}" "${PROJECT_DESCRIPTION}"
create_repo_if_needed "${USER_PAGE_REPO}" "Personal GitHub Pages site for ${OWNER}."
push_project_repo
update_user_page_repo
enable_project_pages_hint
