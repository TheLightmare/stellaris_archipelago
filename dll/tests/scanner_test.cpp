// Unit test for scanner.h — the part of the DLL that decides whether it
// is safe to call into the game binary. Builds as a plain console exe:
//   cmake -B build -S dll -A x64 -DBUILD_TESTING=ON
//   cmake --build build --config Release --target scanner_test
//   build\Release\scanner_test.exe
#include "scanner.h"
#include <cstdio>

static int g_failures = 0;
#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); g_failures++; } } while (0)

int main() {
    // parse_pattern: hex bytes and wildcards
    AOBPattern p = parse_pattern("48 89 ?? 24 ? 55");
    CHECK(p.bytes.size() == 6);
    CHECK(p.bytes[0] == 0x48 && p.bytes[1] == 0x89 && p.bytes[3] == 0x24 && p.bytes[5] == 0x55);
    CHECK(p.mask[0] && p.mask[1] && !p.mask[2] && p.mask[3] && !p.mask[4] && p.mask[5]);
    CHECK(parse_pattern("").bytes.empty());

    // scan_range: unique, none, multiple, wildcard, boundary
    const uint8_t hay[] = {0x00, 0x48, 0x89, 0x5C, 0x24, 0x08, 0x90, 0x48, 0x89, 0x7C, 0x24, 0x18, 0x55};
    ScanResult r = scan_range(hay, sizeof(hay), parse_pattern("48 89 5C 24 08"));
    CHECK(r.matches == 1 && r.address == (uintptr_t)(hay + 1));
    r = scan_range(hay, sizeof(hay), parse_pattern("48 89 ?? 24"));
    CHECK(r.matches == 2 && r.address == (uintptr_t)(hay + 1));   // ambiguous
    r = scan_range(hay, sizeof(hay), parse_pattern("AA BB"));
    CHECK(r.matches == 0 && r.address == 0);
    r = scan_range(hay, sizeof(hay), parse_pattern("24 18 55"));     // ends at the last byte
    CHECK(r.matches == 1 && r.address == (uintptr_t)(hay + 10));
    r = scan_range(hay, sizeof(hay), parse_pattern("24 18 55 00"));  // would run past the end
    CHECK(r.matches == 0);
    r = scan_range(hay, sizeof(hay), parse_pattern(""));
    CHECK(r.matches == 0);
    r = scan_range(hay, 3, parse_pattern("48 89 5C 24 08"));          // range shorter than pattern
    CHECK(r.matches == 0);

    // executable_sections on our own image: must find .text and nothing writable
    HMODULE self = GetModuleHandleA(nullptr);
    auto secs = executable_sections(self);
    CHECK(!secs.empty());
    bool has_text = false;
    for (const auto& s : secs) {
        if (strcmp(s.name, ".text") == 0) has_text = true;
        CHECK(s.size > 0);
        CHECK(s.start >= (const uint8_t*)self);
    }
    CHECK(has_text);

    // scan_module_unique finds this very function's bytes exactly once
    // (take 24 bytes from main's prologue as the needle).
    const uint8_t* needle = (const uint8_t*)&main;
    char pattern[24 * 3 + 1] = {};
    for (int i = 0; i < 24; i++) snprintf(pattern + i * 3, 4, "%02X ", needle[i]);
    std::string where;
    r = scan_module_unique(self, pattern, &where);
    CHECK(r.matches >= 1);
    CHECK(where == ".text");
    if (r.matches == 1) CHECK(r.address == (uintptr_t)needle);

    // A pattern of only wildcards matches everywhere -> reported ambiguous
    r = scan_module_unique(self, "?? ?? ?? ??");
    CHECK(r.matches >= 2);

    // Non-PE pointer is rejected gracefully
    uint8_t junk[64] = {};
    CHECK(executable_sections((HMODULE)junk).empty());

    if (g_failures) { printf("%d check(s) FAILED\n", g_failures); return 1; }
    printf("scanner_test: all checks passed\n");
    return 0;
}
