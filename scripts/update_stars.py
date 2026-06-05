"""Splice srht, GitHub, Codeberg, and GitLab stars into README marker blocks.

GitHub stars are grouped by star list (via GraphQL `viewer.lists`). Repos
starred but not in any list land in an "Uncategorized" section. Codeberg
and GitLab have no list concept, so their sections are flat-alphabetized.
sourcehut content is read verbatim from `srht.md` (hand-curated).

`GITHUB_TOKEN` must be a PAT belonging to the user whose stars are being
listed — `viewer.*` resolves to the token owner. The default
`${{ secrets.GITHUB_TOKEN }}` in CI authenticates as github-actions[bot]
and will not see personal stars/lists, so the workflow uses a separate
secret (e.g. `STARS_GH_TOKEN`).

`CODEBERG_TOKEN` (optional) authenticates against the Forgejo REST API.
The `/users/{u}/starred` endpoint requires authentication even for public
stars. If unset, the Codeberg section is rendered with a notice.

`GITLAB_TOKEN` (optional) authenticates against the GitLab REST API.
If unset, the GitLab section is rendered with a notice.

Output is editorconfig-compliant: UTF-8, LF endings, no trailing
whitespace, no final newline.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

CODEBERG_USER = os.environ.get("CODEBERG_USER", "DivitMittal")
GITLAB_USER = os.environ.get("GITLAB_USER", "DivitMittal")
GITHUB_GRAPHQL = "https://api.github.com/graphql"
CODEBERG_API = "https://codeberg.org/api/v1"
GITLAB_API = "https://gitlab.com/api/v4"
README_PATH = os.environ.get("README_PATH", "README.md")
SRHT_SOURCE = os.environ.get("SRHT_SOURCE", "srht.md")
UA = "awesome-stars-generator"


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def github_graphql(query: str, variables: dict[str, Any], token: str) -> dict[str, Any]:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        GITHUB_GRAPHQL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req) as resp:
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            log(f"  github rate-limit remaining: {remaining}")
        payload = json.loads(resp.read())
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


# Two-pass design: GitHub's GraphQL 502s on the nested lists+items query
# with 28 lists and ~80 items each, so we fetch lists slim first, then
# paginate each list's items via node(id:).
LISTS_QUERY = """
query($listCursor: String) {
  viewer {
    lists(first: 50, after: $listCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id name description }
    }
  }
}
"""

LIST_ITEMS_QUERY = """
query($id: ID!, $itemCursor: String) {
  node(id: $id) {
    ... on UserList {
      items(first: 100, after: $itemCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          ... on Repository {
            nameWithOwner
            url
            description
          }
        }
      }
    }
  }
}
"""

STARS_QUERY = """
query($cursor: String) {
  viewer {
    starredRepositories(first: 100, after: $cursor, orderBy: {field: STARRED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        url
        description
      }
    }
  }
}
"""


def is_repo(node: dict[str, Any]) -> bool:
    return bool(node) and "nameWithOwner" in node


def fetch_list_items(list_id: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = github_graphql(
            LIST_ITEMS_QUERY,
            {"id": list_id, "itemCursor": cursor},
            token,
        )
        conn = data["node"]["items"]
        items.extend(n for n in conn["nodes"] if is_repo(n))
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
    return items


def fetch_github_lists(token: str) -> list[dict[str, Any]] | None:
    """Returns [{name, description, items: [...]}, ...] or None if lists are unavailable."""
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    try:
        while True:
            data = github_graphql(LISTS_QUERY, {"listCursor": cursor}, token)
            conn = data.get("viewer", {}).get("lists")
            if conn is None:
                log("  viewer.lists is null — falling back to flat list")
                return None
            for node in conn["nodes"]:
                log(f"  fetching items for list '{node['name']}'...")
                items = fetch_list_items(node["id"], token)
                out.append(
                    {
                        "name": node["name"],
                        "description": node["description"],
                        "items": items,
                    }
                )
            if not conn["pageInfo"]["hasNextPage"]:
                break
            cursor = conn["pageInfo"]["endCursor"]
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, RuntimeError) as e:
        log(f"  failed to fetch viewer.lists ({e!r}) — falling back to flat")
        return None
    return out


def fetch_github_starred(token: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = github_graphql(STARS_QUERY, {"cursor": cursor}, token)
        conn = data["viewer"]["starredRepositories"]
        out.extend(n for n in conn["nodes"] if is_repo(n))
        if not conn["pageInfo"]["hasNextPage"]:
            break
        cursor = conn["pageInfo"]["endCursor"]
    return out


def fetch_codeberg_starred(token: str | None) -> list[dict[str, Any]]:
    if not token:
        log("  CODEBERG_TOKEN unset — skipping Codeberg fetch")
        return []
    out: list[dict[str, Any]] = []
    page = 1
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Authorization": f"token {token}",
    }
    while True:
        url = f"{CODEBERG_API}/users/{CODEBERG_USER}/starred?limit=50&page={page}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                batch = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            log(f"  codeberg API error on page {page}: {e!r}")
            break
        if not batch:
            break
        for r in batch:
            out.append(
                {
                    "nameWithOwner": r["full_name"],
                    "url": r["html_url"],
                    "description": r.get("description") or "",
                }
            )
        if len(batch) < 50:
            break
        page += 1
    return out


def fetch_gitlab_starred(token: str | None) -> list[dict[str, Any]]:
    if not token:
        log("  GITLAB_TOKEN unset — skipping GitLab fetch")
        return []
    out: list[dict[str, Any]] = []
    page = 1
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    while True:
        url = f"{GITLAB_API}/users/{GITLAB_USER}/starred_projects?per_page=100&page={page}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                batch = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            log(f"  gitlab API error on page {page}: {e!r}")
            break
        if not batch:
            break
        for r in batch:
            out.append(
                {
                    "nameWithOwner": r["path_with_namespace"],
                    "url": r["web_url"],
                    "description": r.get("description") or "",
                }
            )
        if len(batch) < 100:
            break
        page += 1
    return out


def render_entry(repo: dict[str, Any]) -> str:
    name = repo["nameWithOwner"]
    url = repo["url"]
    desc = (repo.get("description") or "").strip()
    return f"- [{name}]({url}) — {desc}" if desc else f"- [{name}]({url})"


def render_repo_section(heading: str, items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return []
    sorted_items = sorted(items, key=lambda x: x["nameWithOwner"].lower())
    n = len(sorted_items)
    label = f"{n} item{'s' if n != 1 else ''}"
    lines = [heading, ""]
    lines += ["<details>", f"<summary>{label}</summary>", ""]
    for r in sorted_items:
        lines.append(render_entry(r))
    lines += ["", "</details>", ""]
    return lines


def build_srht_block() -> str:
    try:
        with open(SRHT_SOURCE, encoding="utf-8") as f:
            return f.read().rstrip()
    except FileNotFoundError:
        log(f"  {SRHT_SOURCE} not found — leaving srht block empty")
        return ""


def build_github_block(
    github_lists: list[dict[str, Any]] | None,
    github_all: list[dict[str, Any]],
) -> str:
    lines: list[str] = ["# [GitHub](https://github.com/)", ""]
    if github_lists is None:
        lines.extend(render_repo_section("## All stars", github_all))
    else:
        in_lists: set[str] = set()
        for lst in github_lists:
            lines.extend(render_repo_section(f"## {lst['name']}", lst["items"]))
            for it in lst["items"]:
                in_lists.add(it["nameWithOwner"])
        uncategorized = [r for r in github_all if r["nameWithOwner"] not in in_lists]
        lines.extend(render_repo_section("## Uncategorized", uncategorized))
    return "\n".join(ln.rstrip() for ln in lines).rstrip()


def build_codeberg_block(codeberg: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# [Codeberg](https://codeberg.org/)", ""]
    if codeberg:
        for r in sorted(codeberg, key=lambda x: x["nameWithOwner"].lower()):
            lines.append(render_entry(r))
    else:
        lines.append("_No starred repos (or `CODEBERG_TOKEN` not configured)._")
    return "\n".join(ln.rstrip() for ln in lines).rstrip()


def build_gitlab_block(gitlab: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# [GitLab](https://gitlab.com/)", ""]
    if gitlab:
        for r in sorted(gitlab, key=lambda x: x["nameWithOwner"].lower()):
            lines.append(render_entry(r))
    else:
        lines.append("_No starred repos (or `GITLAB_TOKEN` not configured)._")
    return "\n".join(ln.rstrip() for ln in lines).rstrip()


def splice_marker(readme: str, name: str, content: str) -> str:
    pattern = re.compile(
        rf"(<!--\s*{name}:START\s*-->)(.*?)(<!--\s*{name}:END\s*-->)",
        re.DOTALL,
    )
    replacement = f"\\1\n{content}\n\\3"
    new, n = pattern.subn(replacement, readme)
    if n == 0:
        raise RuntimeError(f"marker block {name} not found in {README_PATH}")
    return new


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log("error: GITHUB_TOKEN is required")
        return 1

    log("reading srht.md...")
    srht = build_srht_block()

    log("fetching github star lists (graphql)...")
    github_lists = fetch_github_lists(token)
    log("fetching all github starred repos (for uncategorized bucket)...")
    github_all = fetch_github_starred(token)
    log(
        f"github: {len(github_all)} starred, "
        f"{len(github_lists) if github_lists is not None else 0} lists"
    )

    log("fetching codeberg starred repos...")
    codeberg = fetch_codeberg_starred(os.environ.get("CODEBERG_TOKEN"))
    log(f"codeberg: {len(codeberg)} starred")

    log("fetching gitlab starred repos...")
    gitlab = fetch_gitlab_starred(os.environ.get("GITLAB_TOKEN"))
    log(f"gitlab: {len(gitlab)} starred")

    github_block = build_github_block(github_lists, github_all)
    codeberg_block = build_codeberg_block(codeberg)
    gitlab_block = build_gitlab_block(gitlab)

    with open(README_PATH, encoding="utf-8") as f:
        readme = f.read()
    readme = splice_marker(readme, "SRHT", srht)
    readme = splice_marker(readme, "GITHUB", github_block)
    readme = splice_marker(readme, "CODEBERG", codeberg_block)
    readme = splice_marker(readme, "GITLAB", gitlab_block)
    # Trim trailing whitespace per line and drop any final newline.
    readme = "\n".join(ln.rstrip() for ln in readme.split("\n")).rstrip("\n")
    with open(README_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(readme)
    log(f"wrote {README_PATH} ({len(readme)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())