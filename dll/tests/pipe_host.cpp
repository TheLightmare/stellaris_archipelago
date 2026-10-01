// pipe_host.exe — loads a built version.dll the way stellaris.exe does and
// calls one proxied export, which triggers the DLL's deferred init and
// starts its named-pipe server. scripts/check_dll_pipe.py then drives the
// server with the real Python pipe client. No game needed.
//
//   pipe_host.exe <path\to\version.dll> <seconds-to-stay-alive>
#include <windows.h>
#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv) {
    if (argc < 3) { printf("usage: pipe_host <version.dll> <seconds>\n"); return 2; }
    HMODULE dll = LoadLibraryA(argv[1]);
    if (!dll) { printf("LoadLibrary failed: %lu\n", GetLastError()); return 1; }
    auto fn = (DWORD (__stdcall*)(LPCSTR, LPDWORD))GetProcAddress(dll, "GetFileVersionInfoSizeA");
    if (!fn) { printf("export missing\n"); return 1; }
    DWORD handle = 0;
    DWORD size = fn("C:\\Windows\\System32\\kernel32.dll", &handle);
    printf("GetFileVersionInfoSizeA via proxy -> %lu (nonzero means the real DLL was loaded)\n", size);
    fflush(stdout);
    Sleep((DWORD)atoi(argv[2]) * 1000);
    printf("host exiting\n");
    return size ? 0 : 1;
}
