#pragma once
// Protocolo Gaux Link <-> Gaux Live Timer (UDP en 127.0.0.1, little-endian).
//
//  Audio  (plugin -> app, puerto 47654):
//    "GXLK" | u8 version=1 | u8 canales | u16 0 | u32 instancia | u32 secuencia
//    | u32 frecuencia de muestreo | u32 cuadros | float32 intercalados (cuadros x canales)
//  Hola   (plugin -> app, 1 vez por segundo):
//    "GXHI" | u8 version=1 | 3 x u8 0 | u32 instancia | u32 frecuencia | texto UTF-8 "DAW\npista"
//  Recibido (app -> plugin, respuesta al Hola):
//    "GXAK" | u32 instancia que la app está usando
#include <cstdint>

namespace gauxlink
{
    constexpr int appPort = 47654;
    constexpr int maxFramesPerPacket = 480;      // 3.8 KB en estéreo: cabe en un datagrama local
    constexpr int headerBytes = 24;
    constexpr uint8_t version = 1;
}
