// espresso's app executable. macOS signs, notarizes and trusts a Mach-O binary here far more
// readily than a script, so this is one: it finds the launcher script in the bundle's
// Resources and hands over to bash. All the real work stays in launcher.sh.
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void) {
    char exe[PATH_MAX], real[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0 || realpath(exe, real) == NULL) return 1;
    // .../espresso.app/Contents/MacOS/espresso  ->  .../espresso.app/Contents/Resources/launcher.sh
    const char *macos = dirname(real);
    if (snprintf(script, sizeof script, "%s/../Resources/launcher.sh", macos) >= (int)sizeof script) return 1;
    execl("/bin/bash", "bash", script, (char *)NULL);
    perror("espresso: could not start /bin/bash");
    return 1;
}
