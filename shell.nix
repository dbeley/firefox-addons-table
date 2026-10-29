with import <nixpkgs> { };

pkgs.mkShell {
  buildInputs = [
    (pkgs.python312.withPackages (ps:
      with ps; [
        requests
        pandas
        pygithub
        python-gitlab
        beautifulsoup4
        lxml
        urllib3
        pytest
      ]))

    # Used by update-addons-list.sh.
    pkgs.curl
    pkgs.jq

    pkgs.pre-commit
  ];
}
