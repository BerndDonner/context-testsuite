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
              # Use the exact interpreter that carries PyMuPDF and pytest.
              # An unrelated python3 earlier in PATH can lack these modules.
              export CONTEXT_TESTSUITE_PYTHON="${python}/bin/python3"
              export PATH="${python}/bin:$PWD/bin:$PATH"
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
              echo "context-testsuite: 'context-testsuite list' or 'pytest -q'"
            '';
          };
        });
    };
}
