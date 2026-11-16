// DAW falso para las pruebas reales en Mac: una app de verdad, con su ventana titulada como la
// del DAW, que se pone al frente y se cierra sola después de N segundos.
#import <Cocoa/Cocoa.h>
#include <stdlib.h>

int main(int argc, const char **argv) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
        NSString *title = argc > 1 ? [NSString stringWithUTF8String:argv[1]] : @"Untitled";
        double secs = argc > 2 ? atof(argv[2]) : 120.0;
        NSWindow *w = [[NSWindow alloc]
            initWithContentRect:NSMakeRect(160, 140, 1000, 640)
                      styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                                 NSWindowStyleMaskResizable)
                        backing:NSBackingStoreBuffered
                          defer:NO];
        [w setTitle:title];
        [w makeKeyAndOrderFront:nil];
        [NSApp activateIgnoringOtherApps:YES];
        [NSApp performSelector:@selector(terminate:) withObject:nil afterDelay:secs];
        [NSApp run];
    }
    return 0;
}
