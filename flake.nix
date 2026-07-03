{
  description = "taskmaster";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    build-systems.url = "github:pyproject-nix/build-system-pkgs";
  };
  outputs = { self, nixpkgs, uv2nix, pyproject-nix, build-systems }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
    workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
    overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
    python = pkgs.python314;
    pythonSet = (pkgs.callPackage pyproject-nix.build.packages { inherit python; })
      .overrideScope (pkgs.lib.composeManyExtensions [
        build-systems.overlays.default
        overlay
      ]);
    venv = pythonSet.mkVirtualEnv "taskmaster-env" workspace.deps.default;
  in
  {
    packages.${system}.default = venv;
    apps.${system} = {
      server = {
        type = "app";
        program = "${venv}/bin/server";
      };
      client = {
        type = "app";
        program = "${venv}/bin/client";
      };
    };
    devShells.${system}.default = pkgs.mkShell {
      packages = [
        venv
        pkgs.uv
        pkgs.nginx
        pkgs.python3
      ];
    };
  };
}
