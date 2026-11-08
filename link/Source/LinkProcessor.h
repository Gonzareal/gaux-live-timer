#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include <atomic>
#include "LinkProtocol.h"

// Hilo que manda el audio a la app: el hilo de audio del DAW solo copia a una cola sin bloqueos.
class LinkSender : public juce::Thread
{
public:
    LinkSender();
    ~LinkSender() override;

    void setFormat (double sampleRate, int channels);
    void push (const juce::AudioBuffer<float>& buffer, int numSamples) noexcept;   // hilo de audio
    void setNames (const juce::String& host, const juce::String& track);

    enum class Status { waiting, active, standby };
    Status getStatus() const noexcept;
    double getSampleRate() const noexcept { return sampleRate.load(); }
    juce::String getHostName() const;

    void run() override;

private:
    void sendAudio();
    void sendHello();
    void readReplies();

    static constexpr int fifoFrames = 1 << 15;
    juce::AbstractFifo fifo { fifoFrames };
    juce::AudioBuffer<float> ring { 2, fifoFrames };

    juce::DatagramSocket socket { false };
    std::atomic<double> sampleRate { 48000.0 };
    std::atomic<int> numChannels { 2 };
    std::atomic<uint32_t> seq { 0 };
    const uint32_t instanceId;
    std::atomic<juce::int64> lastAckMs { 0 };
    std::atomic<uint32_t> activeId { 0 };
    juce::int64 lastHelloMs = 0;

    mutable juce::CriticalSection nameLock;
    juce::String hostName, trackName;
    juce::HeapBlock<char> packet;
};

class GauxLinkProcessor : public juce::AudioProcessor
{
public:
    GauxLinkProcessor();
    ~GauxLinkProcessor() override = default;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "Gaux Link"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock&) override {}
    void setStateInformation (const void*, int) override {}

    void updateTrackProperties (const TrackProperties& properties) override;

    LinkSender& getSender() noexcept { return sender; }

private:
    LinkSender sender;
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (GauxLinkProcessor)
};
