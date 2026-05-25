{pkgs}: {
  deps = [
    pkgs.python312Packages.tkinter
    pkgs.xvfb-run
    pkgs.xorg.libxcb
    pkgs.xorg.libX11
    pkgs.tk
    pkgs.xorg.xorgserver
  ];
}
