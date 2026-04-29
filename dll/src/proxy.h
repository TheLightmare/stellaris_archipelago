#pragma once
#include <windows.h>

bool proxy_init();
void proxy_shutdown();

extern "C" {
    BOOL __stdcall proxy_GetFileVersionInfoA(LPCSTR, DWORD, DWORD, LPVOID);
    BOOL __stdcall proxy_GetFileVersionInfoByHandle(LPCSTR, DWORD, DWORD, LPVOID);
    BOOL __stdcall proxy_GetFileVersionInfoExA(DWORD, LPCSTR, DWORD, DWORD, LPVOID);
    BOOL __stdcall proxy_GetFileVersionInfoExW(DWORD, LPCWSTR, DWORD, DWORD, LPVOID);
    DWORD __stdcall proxy_GetFileVersionInfoSizeA(LPCSTR, LPDWORD);
    DWORD __stdcall proxy_GetFileVersionInfoSizeExA(DWORD, LPCSTR, LPDWORD);
    DWORD __stdcall proxy_GetFileVersionInfoSizeExW(DWORD, LPCWSTR, LPDWORD);
    DWORD __stdcall proxy_GetFileVersionInfoSizeW(LPCWSTR, LPDWORD);
    BOOL __stdcall proxy_GetFileVersionInfoW(LPCWSTR, DWORD, DWORD, LPVOID);
    DWORD __stdcall proxy_VerFindFileA(DWORD, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT, LPSTR, PUINT);
    DWORD __stdcall proxy_VerFindFileW(DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT, LPWSTR, PUINT);
    DWORD __stdcall proxy_VerInstallFileA(DWORD, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT);
    DWORD __stdcall proxy_VerInstallFileW(DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT);
    DWORD __stdcall proxy_VerLanguageNameA(DWORD, LPSTR, DWORD);
    DWORD __stdcall proxy_VerLanguageNameW(DWORD, LPWSTR, DWORD);
    BOOL __stdcall proxy_VerQueryValueA(LPCVOID, LPCSTR, LPVOID*, PUINT);
    BOOL __stdcall proxy_VerQueryValueW(LPCVOID, LPCWSTR, LPVOID*, PUINT);
}
