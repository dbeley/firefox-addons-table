with import <nixpkgs> { };

pkgs.mkShell {
  buildInputs = [
    pkgs.python311
    python311Packages.pip

    python311Packages.requests
    python311Packages.pandas
    python311Packages.beautifulsoup4
    python311Packages.lxml
    python311Packages.pygithub
    python311Packages.python-gitlab
    python311Packages.urllib3

    pre-commit
  ];

}
