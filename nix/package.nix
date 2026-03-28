{
  lib,
  python3,
  python3Packages,
  symlinkJoin,
  writeShellApplication,
  portaudio,
  stdenv,
  fetchzip,
}:
let
  appId = "ae.socia.Notch";
  src = lib.cleanSource ../.;
  localVosk = python3Packages.callPackage ./vosk.nix { };
  localModel = import ./model.nix { inherit fetchzip; };
  pythonEnv = python3.withPackages (ps: [
    ps.numpy
    ps.pyqt5
    ps.sounddevice
    ps.thefuzz
    localVosk
  ]);
  libraryPath = lib.makeLibraryPath [
    portaudio
    stdenv.cc.cc.lib
  ];
  launcher = writeShellApplication {
    name = "notch";
    runtimeInputs = [ pythonEnv ];
    text = ''
      export LD_LIBRARY_PATH="${libraryPath}:''${LD_LIBRARY_PATH:-}"
      export NOTCH_MODEL_PATH="''${NOTCH_MODEL_PATH:-${localModel}}"
      exec ${pythonEnv}/bin/python ${src}/main.py "$@"
    '';
  };
in
symlinkJoin {
  name = "notch";
  paths = [ launcher ];

  postBuild = ''
    install -Dm644 ${src}/assets/Notch_Clear_1.png "$out/share/pixmaps/${appId}.png"
    install -Dm644 ${./ae.socia.Notch.desktop} "$out/share/applications/${appId}.desktop"
    substituteInPlace "$out/share/applications/${appId}.desktop" \
      --replace-fail '@exec@' "$out/bin/notch"
  '';

  meta = {
    description = "Offline desktop teleprompter";
    homepage = "https://github.com/SultanAlshehhi/Notch";
    license = lib.licenses.mit;
    mainProgram = "notch";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
}
