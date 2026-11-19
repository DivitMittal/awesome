{common-permissions, ...}: let
  checkout-cred = {
    name = "Checkout repo";
    uses = "actions/checkout@main";
    "with" = {
      fetch-depth = 1;
      persist-credentials = true;
    };
  };
  install-nix = {
    name = "Install Nix";
    uses = "nixbuild/nix-quick-install-action@master";
  };
  magic-cache = {
    name = "Magic Nix Cache(Use GitHub Actions Cache)";
    uses = "DeterminateSystems/magic-nix-cache-action@main";
  };
in {
  flake.actions-nix.workflows.".github/workflows/update-stars.yml" = {
    on = {
      workflow_dispatch = {};
      schedule = [
        {
          cron = "0 0 * * 0,3"; # Sun & Wed at 00:00 UTC
        }
      ];
    };
    jobs.refresh-stars = {
      environment.name = "awesome-list";
      permissions = common-permissions;
      steps = [
        checkout-cred
        install-nix
        magic-cache
        {
          name = "Generate stars.md";
          run = "nix run .#update-stars";
          env = {
            ## Token for the account that owns the stars. The default
            ## secrets.GITHUB_TOKEN authenticates as github-actions[bot] and
            ## cannot see personal star lists via viewer.*
            GITHUB_TOKEN = "\${{ secrets.AWESOME_GITHUB_TOKEN }}";
            ## Codeberg API token (any scope) — `/users/{u}/starred` requires auth.
            CODEBERG_TOKEN = "\${{ secrets.AWESOME_CODEBERG_TOKEN }}";
            ## Gitea API token (any scope). Defaults to gitea.com; override
            ## the instance via GITEA_URL if self-hosting.
            GITEA_TOKEN = "\${{ secrets.AWESOME_GITEA_TOKEN }}";
            ## GitLab personal access token (read_api scope).
            GITLAB_TOKEN = "\${{ secrets.AWESOME_GITLAB_TOKEN }}";
          };
        }
        {
          name = "Commit refreshed README.md";
          uses = "stefanzweifel/git-auto-commit-action@v5";
          "with" = {
            commit_message = "docs(stars): refresh GitHub, Codeberg, Gitea & GitLab stars in README";
            file_pattern = "README.md";
          };
        }
      ];
    };
  };
}
