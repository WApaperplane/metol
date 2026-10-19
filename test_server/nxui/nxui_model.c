#include "nxui_model.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The key is only an internal id and the argument handed to the engine script.
 * It is NOT a filename on the camera: /mnt/mmc/looks lives on exFAT, which is
 * case-insensitive, so "samsung_A00.bin" and "samsung_a00.bin" are the same
 * file and cannot be renamed apart with mv ("are the same file").
 *
 * The old rule (a-z 0-9 _ only) therefore made any uppercase, hyphen or CJK
 * look name poison the whole list: nx_load_recipes has all-or-nothing
 * semantics, so one rejected line collapsed all 25 entries to "配方表不可用".
 * Three files named samsung_A00/A01/A02 were enough to blank the LUT panel.
 *
 * Now only structurally impossible keys are refused: '|' is the field
 * separator, control characters break line parsing, and the length must fit.
 * Path separators and shell metacharacters are refused too -- lut.sh joins the
 * key onto $LAB, so "../x" would escape the look library, and a future caller
 * that builds a command string instead of an argv list must not be handed
 * ';', '$' or a backtick. Uppercase, '-', '.', spaces and UTF-8 stay legal. */
int nx_key_valid(const char *s) {
    size_t n = 0;
    if (!s || !*s) return 0;
    for (; *s; s++, n++) {
        unsigned char c = (unsigned char)*s;
        if (c == '|' || c == '/' || c == '\\' || c < 0x20 || c == 0x7f) return 0;
        if (c == ';' || c == '$' || c == '`') return 0;
    }
    return n < sizeof(((struct nx_recipe *)0)->key);
}
static int line_read(FILE *f, char *line, size_t size) {
    size_t n;
    if (!fgets(line, (int)size, f)) return 0;
    n = strlen(line);
    if (n && line[n-1] != '\n' && !feof(f)) return -1;
    line[strcspn(line, "\r\n")] = 0;
    return 1;
}
/* One bad line rejects the whole table (all-or-nothing keeps a half-parsed
 * list from silently driving the camera). That makes the reason matter: a
 * panel that only says "配方表不可用" gives the operator nothing to act on.
 * Every rejection now names the line and the field. */
#define RECIPE_BAD(...) do { \
    fprintf(stderr, "recipes: %s:%d: ", path, lineno); \
    fprintf(stderr, __VA_ARGS__); \
    fputc('\n', stderr); \
    goto bad; \
} while (0)

int nx_load_recipes(const char *path, struct nx_recipe *out, int max) {
    FILE *f = fopen(path, "r");
    char line[1024]; int n = 0, rc, i, j, lineno = 0;
    if (!f) { fprintf(stderr, "recipes: cannot open %s\n", path); return -1; }
    while ((rc = line_read(f, line, sizeof line)) > 0) {
        char *part[9], *p = line, *end;
        struct nx_recipe r;
        ++lineno;
        if (!*line || *line == '#') continue;
        for (i = 0; i < 9; i++) {
            part[i] = p;
            p = strchr(p, '|');
            if (i < 8) { if (!p) break; *p++ = 0; }
            else if (p) break;
        }
        if (i != 9) RECIPE_BAD("expected 9 '|'-separated fields, got %d", i + 1);
        if (!nx_key_valid(part[0])) RECIPE_BAD("bad key '%s'", part[0]);
        if (!*part[1]) RECIPE_BAD("empty label");
        if (strlen(part[1]) >= sizeof r.label) RECIPE_BAD("label too long");
        if (n >= max) RECIPE_BAD("more than %d entries", max);
        for (j = 0; j < n; j++)
            if (!strcmp(out[j].key, part[0])) RECIPE_BAD("duplicate key '%s'", part[0]);
        memset(&r, 0, sizeof r);
        strcpy(r.key, part[0]); strcpy(r.label, part[1]);
        for (i = 0; i < 7; i++) {
            long v;
            if (!*part[i+2]) RECIPE_BAD("field %d is empty", i + 3);
            v = strtol(part[i+2], &end, 10);
            if (*end) RECIPE_BAD("field %d '%s' is not an integer", i + 3, part[i+2]);
            if (v < 0 || v > (i < 3 ? 200 : 20))
                RECIPE_BAD("field %d = %ld out of range 0..%d", i + 3, v, i < 3 ? 200 : 20);
            r.value[i] = (int)v;
        }
        out[n++] = r;
    }
    if (rc < 0) { fprintf(stderr, "recipes: %s:%d: line longer than %zu bytes\n",
                          path, lineno + 1, sizeof line); goto bad; }
    if (ferror(f)) { fprintf(stderr, "recipes: read error on %s\n", path); goto bad; }
    fclose(f); return n;
bad:
    fclose(f); return -1;
}
int nx_load_menu(const char *path, struct nx_item *out, int max) {
    FILE *f = fopen(path, "r"); char line[1024]; int n = 0, rc;
    if (!f) return -1;
    while ((rc = line_read(f, line, sizeof line)) > 0) {
        char *label, *command; int check;
        if (!*line || *line == '#') continue;
        if (!strncmp(line, "button|", 7)) { check = 0; label = line + 7; }
        else if (!strncmp(line, "checkbox|", 9)) { check = 1; label = line + 9; }
        else goto bad;
        command = strchr(label, '|');
        if (!command || n >= max) goto bad;
        *command++ = 0;
        if (strlen(label) >= sizeof out[n].label || strlen(command) >= sizeof out[n].command) goto bad;
        out[n].checkbox = check;
        strcpy(out[n].label, label); strcpy(out[n++].command, command);
    }
    if (rc < 0 || ferror(f)) goto bad;
    fclose(f); return n;
bad:
    fclose(f); return -1;
}
/* Menus can reference only files directly inside the installed scripts folder. */
int nx_menu_path(const char *root, const char *source, char *out, size_t size) {
    const char *p = source; int n;
    if (*p == '@') p++;
    if (!strncmp(p, "/tmp/gui_", 9)) {
        if (strchr(p + 5, '/') || strstr(p, "..")) return 0;
        n = snprintf(out, size, "%s", p);
        return n > 0 && (size_t)n < size;
    }
    if (!strncmp(p, "/opt/usr/nx-ks/", 15)) p += 15;
    if (!*p || strchr(p, '/') || strstr(p, "..") || strchr(p, '\\')) return 0;
    n = snprintf(out, size, "%s/%s", root, p);
    return n > 0 && (size_t)n < size;
}
void nx_queue_init(struct nx_queue *q) {
    memset(q, 0, sizeof *q); q->desired = q->running = q->applied = -1;
}
void nx_queue_select(struct nx_queue *q, int index, long long now) {
    q->desired = index; q->due = now + NXUI_DEBOUNCE_MS;
}
int nx_queue_take(struct nx_queue *q, long long now) {
    if (q->running >= 0 || q->desired < 0 || now < q->due ||
        (q->desired == q->applied && !q->commit_requested)) return -1;
    q->running = q->desired;
    q->committing = q->commit_requested;
    q->commit_requested = 0;
    return q->running;
}
void nx_queue_done(struct nx_queue *q, int success) {
    if (success) q->applied = q->running;
    else if (q->desired == q->running) q->desired = -1; /* explicit retry only */
    q->running = -1;
}
