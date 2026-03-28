{ inputs, lib, ... }:
{
  imports = [ inputs.devshell.flakeModule ];

  perSystem =
    {
      pkgs,
      ...
    }:
    let
      localVosk = pkgs.python3Packages.callPackage ./vosk.nix { };
      localModel = pkgs.callPackage ./model.nix { };
      pythonEnv = pkgs.python3.withPackages (ps: [
        ps.numpy
        ps.pyqt5
        ps.sounddevice
        ps.thefuzz
        localVosk
      ]);
      libraryPath = lib.makeLibraryPath [
        pkgs.portaudio
        pkgs.stdenv.cc.cc.lib
      ];
    in
    {
      devshells.default = {
        devshell = {
          name = "Notch devshell";
          meta.description = "Qt development environment for Notch";
          packages = [
            pythonEnv
            pkgs.pkg-config
            pkgs.portaudio
          ];

          startup.notch-env.text = ''
            export LD_LIBRARY_PATH="${libraryPath}:''${LD_LIBRARY_PATH:-}"
            export NOTCH_MODEL_PATH="''${NOTCH_MODEL_PATH:-${localModel}}"
          '';
        };

        commands = [
          {
            help = "Run Notch from the local checkout";
            name = "notch-run";
            command = "python main.py";
          }
        ];
      };
    };
}
