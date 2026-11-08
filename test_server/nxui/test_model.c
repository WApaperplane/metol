#define _POSIX_C_SOURCE 200809L
#include "nxui_model.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static void fixture(const char *path, const char *data) {
    FILE *f = fopen(path, "w"); assert(f); assert(fputs(data, f) >= 0); assert(!fclose(f));
}
int main(void) {
    char path[] = "/tmp/nxui-model-XXXXXX", out[512];
    struct nx_recipe recipes[4]; struct nx_item items[4]; struct nx_queue q;
    int fd = mkstemp(path); assert(fd >= 0); close(fd);
    assert(nx_key_valid("portra400")); assert(!nx_key_valid("x;reboot"));
    assert(!nx_key_valid("../x")); assert(!nx_key_valid(""));
    fixture(path, "portra400|Portra 400|106|100|93|11|9|9|8\r\ntrix400|黑白|100|100|100|10|0|13|12\n");
    assert(nx_load_recipes(path, recipes, 4) == 2); assert(recipes[1].value[4] == 0);
    fixture(path, "x;reboot|X|100|100|100|10|10|10|10\n");
    assert(nx_load_recipes(path, recipes, 4) == -1);
    fixture(path, "x|X|100|100|100|10||10|10\n");
    assert(nx_load_recipes(path, recipes, 4) == -1);
    fixture(path, "x|X|100|100|100|10|21|10|10\n");
    assert(nx_load_recipes(path, recipes, 4) == -1);
    fixture(path, "x|X|100|100|100|10|10|10|10\nx|Y|100|100|100|10|10|10|10\n");
    assert(nx_load_recipes(path, recipes, 4) == -1);
    fixture(path, "button|设置|@/opt/usr/nx-ks/gui_settings.NX500\ncheckbox|远程控制|nx-rc.sh\n");
    assert(nx_load_menu(path, items, 4) == 2); assert(items[1].checkbox == 1);
    assert(nx_menu_path("/new", "@/opt/usr/nx-ks/gui_ini.NX500", out, sizeof out));
    assert(!strcmp(out, "/new/gui_ini.NX500"));
    assert(nx_menu_path("/new", "@/tmp/gui_br.NX500", out, sizeof out));
    assert(!nx_menu_path("/new", "@../../etc/passwd", out, sizeof out));
    assert(!nx_menu_path("/new", "@/tmp/gui_x/../../etc/passwd", out, sizeof out));
    nx_queue_init(&q);
    nx_queue_select(&q, 0, 1000); assert(nx_queue_take(&q, 1100) == -1);
    nx_queue_select(&q, 1, 1210); nx_queue_select(&q, 2, 1220);
    assert(nx_queue_take(&q, 1470) == 2);
    nx_queue_select(&q, 3, 1480); assert(nx_queue_take(&q, 1800) == -1);
    nx_queue_done(&q, 1); assert(q.applied == 2); assert(nx_queue_take(&q, 1800) == 3);
    nx_queue_done(&q, 0); assert(q.applied == 2); assert(nx_queue_take(&q, 2000) == -1);
    nx_queue_select(&q, 3, 2000); q.commit_requested = 1;
    assert(nx_queue_take(&q, 2250) == 3); assert(q.committing);
    nx_queue_done(&q, 1); assert(q.applied == 3);
    assert(nx_queue_take(&q, 3000) == -1); /* no idle reapply */
    /* LUT 模式：同一串快速选择在 450 ms 内都不该落地，只留最后一次 */
    nx_queue_init(&q);
    assert(q.debounce_ms == NXUI_DEBOUNCE_MS);
    q.debounce_ms = NXUI_LUT_DEBOUNCE_MS;
    nx_queue_select(&q, 0, 1000); assert(nx_queue_take(&q, 1400) == -1);
    nx_queue_select(&q, 1, 1300); assert(nx_queue_take(&q, 1700) == -1); /* due=1750 */
    assert(nx_queue_take(&q, 1750) == 1);
    nx_queue_done(&q, 1);
    /* 显式确认（OK / 保存并关闭）跳过去抖 */
    nx_queue_select_now(&q, 2, 2000); assert(nx_queue_take(&q, 2000) == 2);
    unlink(path); puts("PASS recipe/menu parsing, traversal rejection, debounce, serialization, failure/retry, commit");
    return 0;
}
