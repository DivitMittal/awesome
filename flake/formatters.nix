{inputs, ...}: {
  imports = [inputs.treefmt-nix.flakeModule];

  perSystem.treefmt = {
    projectRootFile = "flake.nix";
    settings.global = {
      excludes = [
        ".github/*"
        "README.md"
        "srht.md"
      ];
    };

    flakeCheck = false;

    programs = {
      ## Nix
      alejandra.enable = true;
      deadnix.enable = true;
      statix.enable = true;
      ## Markdown
      mdformat.enable = true;
    };
  };
}