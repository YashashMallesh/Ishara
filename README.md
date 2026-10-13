# Swipe — Minimalist Touchless Presentation Controller 🖐️👀

A sleek, distraction-free slide presentation web application powered by **MediaPipe**, **OpenCV**, **Flask**, and **PyAutoGUI**. Control your slideshows hands-free using hand gestures, dynamic swipes, or eye gaze tracking.

---

## ✨ What's New: Minimalist Design & Custom PPT / Slide Insertion

1. **Minimalist, Distraction-Free Interface**:
   - Clean, elegant typography and generous whitespace designed for presentation focus (Keynote / Linear aesthetic).
   - High-impact 16:9 presentation stage with subtle dark themes.
   - Picture-in-Picture (PiP) floating camera widget in the corner (can be collapsed or expanded anytime).

2. **Insert Custom Slides or PPT**:
   - **Microsoft PowerPoint (`.pptx`)**: Drag & drop any `.pptx` file. Slides, titles, and bullet points are parsed automatically into native slides.
   - **Adobe PDF (`.pdf`)**: Drag & drop any `.pdf` presentation. Rendered with vector sharpness via PDF.js.
   - **Slide Images (`.png`, `.jpg`, `.jpeg`, `.webp`)**: Upload full-bleed slide images.
   - **Custom Slide Creator**: Write slides directly with custom titles, categories, bullet points, and minimalist themes (Dark, Slate, Indigo, Emerald).

---

## 🚀 Quick Start

### 1. Launch with One Click
Double-click `run_webapp.bat` or run:
```bash
.\run_webapp.bat
```
Opens **[http://localhost:5000](http://localhost:5000)** in your browser.

---

## 🖐️ Hand Gestures Reference

| Gesture | Action | Hold Time | Keyboard Key |
| :--- | :--- | :--- | :--- |
| **👉 Index Finger** | Next Slide | 0.4s | `Right Arrow` (→) |
| **✌️ Two Fingers** | Previous Slide | 0.4s | `Left Arrow` (←) |
| **💨 Horizontal Swipe** | Quick Advance | Instant | `Right` / `Left` |
| **✊ Closed Fist** | Lock / Unlock (Armed) | 1.5s | Toggle |
| **🤟 Three Fingers** | Screen Blackout | 0.6s | `b` |

---

## 👀 Eye Gaze Reference

| Direction | Action | Description |
| :--- | :--- | :--- |
| **👉 Look Right** | Next Slide | Hold gaze right for 0.8s |
| **👈 Look Left** | Previous Slide | Hold gaze left for 0.8s |
| **👀 Center Gaze** | Rearm | Return eyes to center to enable the next slide command |

---

## ⌨️ Keyboard Shortcuts
- `Right Arrow` / `Space` / `Page Down`: Next Slide
- `Left Arrow` / `Page Up`: Previous Slide
- `F`: Toggle Fullscreen Presentation Mode
- `B`: Toggle Screen Blackout
- `Home` / `End`: Jump to First / Last Slide
