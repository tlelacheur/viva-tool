{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    python311Packages.pip
    python311Packages.virtualenv
    nodejs_20
    nodePackages.npm
    docker
    docker-compose
    curl
    jq
  ];

  shellHook = ''
    if [ ! -d ".venv" ]; then
      python3 -m venv .venv
    fi
    source .venv/bin/activate
    echo "NixOS environment ready. Python virtualenv activated."
  '';
}