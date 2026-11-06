#include <CoreFoundation/CoreFoundation.h>
#include <CoreText/CoreText.h>
#include <stdio.h>
#include <string.h>
// Register only for this login session, without installing or replacing user fonts.
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    CFURLRef url = CFURLCreateFromFileSystemRepresentation(NULL, (const UInt8 *)argv[1], strlen(argv[1]), false);
    if (!url) return 3;
    CFErrorRef error = NULL;
    Boolean ok = CTFontManagerRegisterFontsForURL(url, kCTFontManagerScopeSession, &error);
    CFIndex code = error ? CFErrorGetCode(error) : 0;
    CFRelease(url);
    if (error) CFRelease(error);
    if (!ok && code != kCTFontManagerErrorAlreadyRegistered) { fprintf(stderr, "Font registration failed: %ld\n", (long)code); return 4; }
    puts("{\"session_font_registered\":true,\"persistent_install\":false}");
    return 0;
}
