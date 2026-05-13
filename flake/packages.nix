{...}: {
  perSystem = {pkgs, ...}: {
    packages.update-stars = pkgs.writers.writePython3Bin "update-stars" {
      flakeIgnore = [
        "E501" # line too long
        "W503" # line break before binary operator
        "W504" # line break after binary operator
        "W292" # no newline at end of file (intentional, per .editorconfig)
        "E203" # whitespace before ':'
        "E731" # lambda assignment
        "E741" # ambiguous variable name
      ];
    } (builtins.readFile ../scripts/update_stars.py);
  };
}