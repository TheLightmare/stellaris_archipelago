// scanner.h — AOB (array-of-bytes) pattern scanning over a loaded module.
//
// Header-only so dll/tests/scanner_test.cpp can exercise it without the
// rest of the DLL. Two properties matter for safety:
//
//   * Only executable PE sections are scanned. Data sections can't hold
//     the functions we want, and scanning the whole SizeOfImage range can
//     touch pages that are not readable.
//   * Matches are counted, not just found. A pattern that matches more
//     than once after a game update is ambiguous; calling the wrong
//     function with an engine string crashes the game, so the caller
//     must treat "ambiguous" exactly like "not found".
#pragma once
#include <windows.h>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <string>
#include <vector>

struct AOBPattern {
    std::vector<uint8_t> bytes;
    std::vector<bool> mask; // true = must match, false = wildcard
};

inline AOBPattern parse_pattern(const char* pat) {
    AOBPattern p;
    std::istringstream iss(pat);
    std::string token;
    while (iss >> token) {
        if (token == "??" || token == "?") {
            p.bytes.push_back(0);
            p.mask.push_back(false);
        } else {
            p.bytes.push_back((uint8_t)strtoul(token.c_str(), nullptr, 16));
            p.mask.push_back(true);
        }
    }
    return p;
}

struct ScanResult {
    uintptr_t address = 0; // first match (0 if none)
    size_t matches = 0;    // total matches found (capped at stop_after)
};

// Scan [base, base+size). Stops counting once `stop_after` matches are
// seen — two is enough to know a pattern is not unique.
inline ScanResult scan_range(const uint8_t* base, size_t size, const AOBPattern& pat,
                             size_t stop_after = 2) {
    ScanResult r;
    const size_t n = pat.bytes.size();
    if (n == 0 || size < n) return r;
    for (size_t i = 0; i + n <= size; i++) {
        bool match = true;
        for (size_t j = 0; j < n; j++) {
            if (pat.mask[j] && base[i + j] != pat.bytes[j]) { match = false; break; }
        }
        if (match) {
            if (r.matches == 0) r.address = (uintptr_t)(base + i);
            if (++r.matches >= stop_after) break;
        }
    }
    return r;
}

struct ModuleSection {
    const uint8_t* start;
    size_t size;
    char name[9];
};

// Executable sections of a loaded PE image (typically just ".text").
inline std::vector<ModuleSection> executable_sections(HMODULE mod) {
    std::vector<ModuleSection> out;
    auto base = (const uint8_t*)mod;
    if (!base) return out;
    auto dos = (const IMAGE_DOS_HEADER*)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return out;
    auto nt = (const IMAGE_NT_HEADERS*)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return out;
    auto sec = IMAGE_FIRST_SECTION(nt);
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; i++) {
        if (!(sec[i].Characteristics & IMAGE_SCN_MEM_EXECUTE)) continue;
        ModuleSection s{};
        s.start = base + sec[i].VirtualAddress;
        s.size = sec[i].Misc.VirtualSize;
        memcpy(s.name, sec[i].Name, 8);
        s.name[8] = 0;
        out.push_back(s);
    }
    return out;
}

// Scan every executable section of `mod`. `where` (optional) receives the
// section name of the first match.
inline ScanResult scan_module_unique(HMODULE mod, const char* pattern_str,
                                     std::string* where = nullptr) {
    ScanResult total;
    AOBPattern pat = parse_pattern(pattern_str);
    for (const auto& s : executable_sections(mod)) {
        ScanResult r = scan_range(s.start, s.size, pat);
        if (r.matches && total.matches == 0) {
            total.address = r.address;
            if (where) *where = s.name;
        }
        total.matches += r.matches;
        if (total.matches >= 2) break;
    }
    return total;
}
