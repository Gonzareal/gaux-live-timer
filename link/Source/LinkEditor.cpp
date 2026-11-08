#include "LinkEditor.h"

namespace
{
    juce::String u8 (const char* t) { return juce::String (juce::CharPointer_UTF8 (t)); }

    const juce::Colour black   (0xff0a0a0a);
    const juce::Colour smoke   (0xff2a2a2a);
    const juce::Colour red     (0xffd2050f);
    const juce::Colour white   (0xfff0f0f0);
    const juce::Colour dim     (0xff8a8a8a);
}

GauxLinkEditor::GauxLinkEditor (GauxLinkProcessor& p) : AudioProcessorEditor (p), proc (p)
{
    setSize (400, 170);
    startTimerHz (20);
}

void GauxLinkEditor::timerCallback()
{
    const auto s = proc.getSender().getStatus();
    pulse += 0.12f;
    if (s == LinkSender::Status::active || s != last)
        repaint();
    last = s;
}

void GauxLinkEditor::paint (juce::Graphics& g)
{
    g.fillAll (black);
    auto r = getLocalBounds().reduced (22, 18);

    // marca
    juce::Font big (juce::FontOptions (30.0f, juce::Font::bold));
    g.setFont (big);
    g.setColour (white);
    const int wGaux = juce::GlyphArrangement::getStringWidthInt (big, "GAUX ");
    g.drawText ("GAUX", r.getX(), r.getY(), wGaux, 34, juce::Justification::centredLeft);
    g.setColour (red);
    g.drawText ("LINK", r.getX() + wGaux, r.getY(), 120, 34, juce::Justification::centredLeft);

    // rayo
    juce::Path bolt;
    const float bx = (float) r.getRight() - 26.0f, by = (float) r.getY() + 2.0f, k = 0.075f;
    const float pts[] = { 40, -215, -105, 25, -5, 25, -45, 215, 110, -30, 10, -30 };
    bolt.startNewSubPath (bx + pts[0] * k, by + 16 + pts[1] * k);
    for (int i = 2; i < 12; i += 2)
        bolt.lineTo (bx + pts[i] * k, by + 16 + pts[i + 1] * k);
    bolt.closeSubPath();
    g.setColour (red);
    g.fillPath (bolt);

    // estado
    auto& s = proc.getSender();
    const auto st = s.getStatus();
    juce::String title, sub;
    juce::Colour dot = dim;
    if (st == LinkSender::Status::active)
    {
        title = "Enviando a Gaux Live Timer";
        dot = red.withAlpha (0.65f + 0.35f * std::sin (pulse));
        sub = s.getHostName() + u8 ("  ·  ") + juce::String (s.getSampleRate() / 1000.0, 1) + " kHz";
    }
    else if (st == LinkSender::Status::standby)
    {
        title = "En espera";
        dot = juce::Colour (0xffe0a020);
        sub = u8 ("Otra pista ya está enviando. Deja Gaux Link solo en el Master.");
    }
    else
    {
        title = "Abre Gaux Live Timer";
        sub = u8 ("Con la app abierta y el analizador activo, recibe este audio.");
    }
    auto row = r.withTrimmedTop (50).withHeight (24);
    g.setColour (dot);
    g.fillEllipse ((float) row.getX(), (float) row.getCentreY() - 6.0f, 12.0f, 12.0f);
    g.setColour (white);
    g.setFont (juce::FontOptions (16.0f, juce::Font::bold));
    g.drawText (title, row.withTrimmedLeft (22), juce::Justification::centredLeft);
    g.setColour (dim);
    g.setFont (juce::FontOptions (13.0f));
    g.drawFittedText (sub, r.withTrimmedTop (78).withHeight (20).withTrimmedLeft (22),
                      juce::Justification::centredLeft, 1);

    g.setColour (smoke);
    g.fillRect (r.getX(), r.getBottom() - 30, r.getWidth(), 1);
    g.setColour (dim);
    g.setFont (juce::FontOptions (12.0f));
    g.drawText ("Ponlo al final del Master. No modifica tu audio.",
                r.withTop (r.getBottom() - 24), juce::Justification::centredLeft);
}
