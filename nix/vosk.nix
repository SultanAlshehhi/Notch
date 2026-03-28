{
  lib,
  autoPatchelfHook,
  buildPythonPackage,
  cffi,
  fetchPypi,
  requests,
  srt,
  stdenv,
  tqdm,
  websockets,
}:
let
  wheel =
    if stdenv.hostPlatform.system == "x86_64-linux" then
      {
        platform = "manylinux_2_12_x86_64.manylinux2010_x86_64";
        hash = "sha256-JeAlCTxDmdcnj1Q1aO2MxUYKw6S/SMI2c6zh4l0mYZ8=";
      }
    else if stdenv.hostPlatform.system == "aarch64-linux" then
      {
        platform = "manylinux2014_aarch64";
        hash = "sha256-VO+0fdiQ5UTp4g8DFkE6zsf4aA0E7AlcYUCrTnAmJwQ=";
      }
    else
      throw "Unsupported platform for vosk: ${stdenv.hostPlatform.system}";
in
buildPythonPackage rec {
  pname = "vosk";
  version = "0.3.45";
  format = "wheel";

  src = fetchPypi {
    inherit pname version format;
    python = "py3";
    dist = "py3";
    inherit (wheel) platform hash;
  };

  nativeBuildInputs = [ autoPatchelfHook ];

  buildInputs = [ stdenv.cc.cc.lib ];

  propagatedBuildInputs = [
    cffi
    requests
    srt
    tqdm
    websockets
  ];

  pythonImportsCheck = [ ];

  meta = {
    description = "Offline open source speech recognition toolkit";
    homepage = "https://alphacephei.com/vosk/";
    license = lib.licenses.asl20;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
}
