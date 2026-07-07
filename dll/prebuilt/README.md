# Prebuilt bridge DLL

`version.dll` is the compiled Stellaris bridge (statically linked, no
VC++ redistributable needed) so players can install without CMake or
Visual Studio. `python setup.py install` / `install-dll` uses it
automatically when you haven't built the DLL yourself.

To rebuild from source instead:

```powershell
python setup.py build-dll     # requires CMake + Visual Studio 2022
python setup.py install-dll   # a fresh local build takes priority over this file
```

Maintainers: refresh this binary after changing anything under
`dll/src/` (`python setup.py build-dll`, then copy
`dll/build/Release/version.dll` here).
