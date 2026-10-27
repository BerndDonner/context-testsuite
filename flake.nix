{
  description = "Independent Python development environment for ConTeXt regression tests";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));
    in
    {
      devShells = forAllSystems (pkgs:
        let
          python = pkgs.python3.withPackages (ps: [ ps.pymupdf ps.pytest ]);
        in
        {
          default = pkgs.mkShell {
            packages = [ python pkgs.poppler-utils ];
            shellHook = ''
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
              export PATH="$PWD/bin:$PATH"
              echo "context-testsuite: 'context-testsuite list' or 'pytest -q'"
            '';
          };
        });
    };
}
