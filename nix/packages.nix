{ ... }:
{
  perSystem =
    { pkgs, ... }:
    let
      package = pkgs.callPackage ./package.nix { };
    in
    {
      packages = {
        default = package;
        notch = package;
      };
    };
}
