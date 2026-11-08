#include "LinkProcessor.h"
#include "LinkEditor.h"
#include <cstring>

using namespace gauxlink;

static void put32 (char* p, uint32_t v) noexcept { std::memcpy (p, &v, 4); }   // little-endian (x86/ARM)

// ============================================================================
LinkSender::LinkSender()
    : juce::Thread ("Gaux Link"),
      instanceId ((uint32_t) juce::Random::getSystemRandom().nextInt() | 1u)
{
    packet.allocate ((size_t) (headerBytes + maxFramesPerPacket * 2 * 4 + 64), true);
    hostName = juce::PluginHostType().getHostDescription();
    socket.bindToPort (0, "127.0.0.1");            // puerto propio para recibir la respuesta de la app
    startThread (juce::Thread::Priority::low);
}

LinkSender::~LinkSender()
{
    signalThreadShouldExit();
    socket.shutdown();
    stopThread (2000);
}

void LinkSender::setFormat (double sr, int channels)
{
    sampleRate.store (sr > 0 ? sr : 48000.0);
    numChannels.store (juce::jlimit (1, 2, channels));
    fifo.reset();
}

void LinkSender::push (const juce::AudioBuffer<float>& buffer, int numSamples) noexcept
{
    const int ch = juce::jmin (buffer.getNumChannels(), 2);
    if (ch <= 0 || numSamples <= 0)
        return;
    int s1, n1, s2, n2;
    fifo.prepareToWrite (numSamples, s1, n1, s2, n2);     // si la cola está llena, se descarta
    for (int c = 0; c < 2; ++c)
    {
        const int src = juce::jmin (c, ch - 1);            // mono: se duplica
        if (n1 > 0) ring.copyFrom (c, s1, buffer, src, 0, n1);
        if (n2 > 0) ring.copyFrom (c, s2, buffer, src, n1, n2);
    }
    fifo.finishedWrite (n1 + n2);
}

void LinkSender::setNames (const juce::String& host, const juce::String& track)
{
    const juce::ScopedLock sl (nameLock);
    if (host.isNotEmpty()) hostName = host;
    trackName = track;
}

juce::String LinkSender::getHostName() const
{
    const juce::ScopedLock sl (nameLock);
    return hostName;
}

LinkSender::Status LinkSender::getStatus() const noexcept
{
    if (juce::Time::currentTimeMillis() - lastAckMs.load() > 2500)
        return Status::waiting;
    return activeId.load() == instanceId ? Status::active : Status::standby;
}

void LinkSender::run()
{
    while (! threadShouldExit())
    {
        sendAudio();
        const auto now = juce::Time::currentTimeMillis();
        if (now - lastHelloMs >= 1000)
        {
            lastHelloMs = now;
            sendHello();
        }
        readReplies();
        wait (5);
    }
}

void LinkSender::sendAudio()
{
    const bool appListening = juce::Time::currentTimeMillis() - lastAckMs.load() < 5000;
    while (fifo.getNumReady() > 0 && ! threadShouldExit())
    {
        const int frames = juce::jmin (fifo.getNumReady(), maxFramesPerPacket);
        int s1, n1, s2, n2;
        fifo.prepareToRead (frames, s1, n1, s2, n2);
        if (appListening)          // sin la app abierta no se manda nada: cero trabajo extra
        {
            char* p = packet.get();
            std::memcpy (p, "GXLK", 4);
            p[4] = (char) version;
            p[5] = 2;
            p[6] = p[7] = 0;
            put32 (p + 8, instanceId);
            put32 (p + 12, seq.fetch_add (1));
            put32 (p + 16, (uint32_t) std::lround (sampleRate.load()));
            put32 (p + 20, (uint32_t) frames);
            auto* out = reinterpret_cast<float*> (p + headerBytes);
            auto copy = [&] (int start, int n)
            {
                const float* l = ring.getReadPointer (0, start);
                const float* r = ring.getReadPointer (1, start);
                for (int i = 0; i < n; ++i) { *out++ = l[i]; *out++ = r[i]; }
            };
            copy (s1, n1);
            copy (s2, n2);
            socket.write ("127.0.0.1", appPort, p, headerBytes + frames * 2 * 4);
        }
        fifo.finishedRead (n1 + n2);
    }
}

void LinkSender::sendHello()
{
    juce::String host, track;
    {
        const juce::ScopedLock sl (nameLock);
        host = hostName;
        track = trackName;
    }
    const auto text = (host + "\n" + track).toStdString();
    char* p = packet.get();
    std::memcpy (p, "GXHI", 4);
    p[4] = (char) version;
    p[5] = p[6] = p[7] = 0;
    put32 (p + 8, instanceId);
    put32 (p + 12, (uint32_t) std::lround (sampleRate.load()));
    const int len = (int) juce::jmin<size_t> (text.size(), 200);
    std::memcpy (p + 16, text.data(), (size_t) len);
    socket.write ("127.0.0.1", appPort, p, 16 + len);
}

void LinkSender::readReplies()
{
    char buf[64];
    while (socket.waitUntilReady (true, 0) == 1)
    {
        const int n = socket.read (buf, (int) sizeof (buf), false);
        if (n < 8)
            break;
        if (std::memcmp (buf, "GXAK", 4) == 0)
        {
            uint32_t id;
            std::memcpy (&id, buf + 4, 4);
            activeId.store (id);
            lastAckMs.store (juce::Time::currentTimeMillis());
        }
    }
}

// ============================================================================
GauxLinkProcessor::GauxLinkProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Entrada", juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Salida", juce::AudioChannelSet::stereo(), true))
{
}

bool GauxLinkProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    const auto out = layouts.getMainOutputChannelSet();
    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo())
        return false;
    return layouts.getMainInputChannelSet() == out;
}

void GauxLinkProcessor::prepareToPlay (double sampleRate, int)
{
    sender.setFormat (sampleRate, getTotalNumInputChannels());
}

void GauxLinkProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    // el audio pasa igual: solo se copia
    sender.push (buffer, buffer.getNumSamples());
}

void GauxLinkProcessor::updateTrackProperties (const TrackProperties& properties)
{
    sender.setNames ({}, properties.name.value_or (juce::String()));
}

juce::AudioProcessorEditor* GauxLinkProcessor::createEditor()
{
    return new GauxLinkEditor (*this);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new GauxLinkProcessor();
}
