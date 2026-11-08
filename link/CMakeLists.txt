cmake_minimum_required(VERSION 3.22)

# Gaux Link: plugin mínimo que pasa el audio sin tocarlo y le envía una copia a
# Gaux Live Timer (por la red interna del computador, 127.0.0.1). Así el analizador
# no necesita BlackHole ni VB-Cable.
project(GauxLink VERSION 1.0.0)

set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
if(APPLE AND NOT CMAKE_OSX_ARCHITECTURES)
    set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "" FORCE)
endif()
set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "Version minima de macOS")

if(DEFINED JUCE_DIR)
    add_subdirectory(${JUCE_DIR} JUCE)
else()
    include(FetchContent)
    FetchContent_Declare(JUCE
        GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
        GIT_TAG 9.0.4
        GIT_SHALLOW TRUE)
    FetchContent_MakeAvailable(JUCE)
endif()

set(LINK_FORMATS VST3)
if(APPLE)
    list(APPEND LINK_FORMATS AU)
endif()

juce_add_plugin(GauxLink
    COMPANY_NAME "Gaux"
    BUNDLE_ID "com.gaux.link"
    PLUGIN_MANUFACTURER_CODE Gaux
    PLUGIN_CODE Gxlk
    FORMATS ${LINK_FORMATS}
    PRODUCT_NAME "Gaux Link"
    DESCRIPTION "Envia el audio a Gaux Live Timer"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD FALSE
    VST3_CATEGORIES Fx Analyzer
    AU_MAIN_TYPE kAudioUnitType_Effect
    NEEDS_WEB_BROWSER FALSE
    NEEDS_CURL FALSE)

target_compile_features(GauxLink PRIVATE cxx_std_17)
if(MSVC)
    set_property(TARGET GauxLink PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    target_compile_options(GauxLink PRIVATE /MP)
    target_compile_definitions(GauxLink PRIVATE NOMINMAX)
endif()

target_sources(GauxLink PRIVATE
    Source/LinkProcessor.cpp
    Source/LinkEditor.cpp)

target_compile_definitions(GauxLink PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_DISPLAY_SPLASH_SCREEN=0)

target_link_libraries(GauxLink
    PRIVATE
        juce::juce_audio_processors
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags)
