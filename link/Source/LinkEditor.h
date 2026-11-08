#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include "LinkProcessor.h"

class GauxLinkEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit GauxLinkEditor (GauxLinkProcessor&);
    void paint (juce::Graphics&) override;

private:
    void timerCallback() override;
    GauxLinkProcessor& proc;
    float pulse = 0.0f;
    LinkSender::Status last = LinkSender::Status::waiting;
};
