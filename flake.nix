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
            packages = [ python ];
            shellHook = ''
              # The Python environment must win over unrelated Python executables
              # from the surrounding shell or other packages. pytest already
              # uses this environment, and CLI subprocesses must use it too.
              export PATH="${python}/bin:$PWD/bin:$PATH"
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
              echo "context-testsuite: list | run --help | python -m pytest -q"
            '';
          };
        });
    };
}
