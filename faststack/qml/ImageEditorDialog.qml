pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

Window {
    id: imageEditorDialog
    width: 800
    height: 820
    property var uiStateRef: null
    property var controllerRef: null
    title: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.editorFilename ? "Image Editor - " + imageEditorDialog.uiStateRef.editorFilename + " (" + imageEditorDialog.uiStateRef.editorBitDepth + "-bit)" : "Image Editor"
    visible: imageEditorDialog.uiStateRef ? imageEditorDialog.uiStateRef.isEditorOpen : false
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
    property int updatePulse: 0
    property color backgroundColor: "#1e1e1e" // Default dark background
    property color textColor: "white" // Default text color

    // Modern Color Palette
    readonly property color accentColor: "#6366f1" // Modern Indigo
    readonly property color accentColorHover: "#818cf8"
    readonly property color accentColorSubtle: "#306366f1"
    readonly property color controlBg: "#10ffffff"
    readonly property color controlBorder: "#30ffffff"
    readonly property color separatorColor: "#20ffffff"

    Component.onCompleted: {
        imageEditorDialog.uiStateRef = uiState
        imageEditorDialog.controllerRef = controller
    }

    Material.theme: (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.theme === 0) ? Material.Dark : Material.Light
    Material.accent: accentColor

    onClosing: (close) => {
        if (imageEditorDialog.uiStateRef) imageEditorDialog.uiStateRef.isEditorOpen = false
    }

    onVisibleChanged: {
        if (visible && imageEditorDialog.controllerRef) {
            imageEditorDialog.controllerRef.update_histogram()
        }
    }
    
    // Auto-update histogram when pulse changes (buttons, double-taps, spinbox)
    onUpdatePulseChanged: {
        if (visible && imageEditorDialog.controllerRef) {
            imageEditorDialog.controllerRef.update_histogram()
        }
    }

    property int slidersPressedCount: 0
    onSlidersPressedCountChanged: {
        if (imageEditorDialog.uiStateRef) imageEditorDialog.uiStateRef.setAnySliderPressed(slidersPressedCount > 0)
    }

    function getBackendValue(key) {
        var _dependency = updatePulse;
        if (imageEditorDialog.uiStateRef && key in imageEditorDialog.uiStateRef) return imageEditorDialog.uiStateRef[key];
        return 0.0;
    }

    // Background
    color: imageEditorDialog.backgroundColor

    Shortcut {
        sequence: "Escape"
        context: Qt.WindowShortcut
        onActivated: {
            if (imageEditorDialog.uiStateRef) imageEditorDialog.uiStateRef.isEditorOpen = false
        }
    }
    Shortcut {
        sequence: "S"
        context: Qt.WindowShortcut
        enabled: imageEditorDialog.uiStateRef ? !imageEditorDialog.uiStateRef.isSaving : true
        onActivated: {
            if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.save_edited_image()
            // Note: Editor closes automatically via _on_save_finished callback
        }
    }
    Shortcut {
        sequence: "K"
        context: Qt.WindowShortcut
        onActivated: {
            if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.toggle_darken_mode()
        }
    }

    // Component for Section Separator
    Component {
        id: sectionSeparator
        Rectangle {
            Layout.fillWidth: true
            Layout.topMargin: 20
            Layout.bottomMargin: 5
            height: 1
            color: imageEditorDialog.separatorColor
        }
    }

    // Component for Section Header
    Component {
        id: sectionHeader
        Label {
            font.bold: true
            font.pixelSize: 15
            font.letterSpacing: 1.0
            color: imageEditorDialog.accentColorHover
            Layout.topMargin: 5
            Layout.bottomMargin: 10
        }
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: 10
        anchors.topMargin: 5
        clip: true
        contentWidth: availableWidth

        RowLayout {
            width: parent.width
            spacing: 30

            // --- LEFT COLUMN ---
            ColumnLayout { 
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 30) / 2
                Layout.alignment: Qt.AlignTop
                spacing: 15

                // --- Light Group ---
                Loader { 
                    sourceComponent: sectionHeader 
                    Layout.topMargin: 0 // Remove top margin for the very first item
                    onLoaded: item.text = "☀ Light"
                }
                ListModel {
                    id: lightModel
                    ListElement { name: "Exposure"; key: "exposure"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Brightness"; key: "brightness"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Highlights"; key: "highlights"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Whites"; key: "whites"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Shadows"; key: "shadows"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Blacks"; key: "blacks"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Contrast"; key: "contrast"; reverse: false; min: -100; max: 100 }
                }
                Repeater { model: lightModel; delegate: editSlider }

                Loader { sourceComponent: sectionSeparator }

                // --- Detail Group ---
                Loader { 
                    sourceComponent: sectionHeader
                    onLoaded: item.text = "🔍 Detail"
                }
                ListModel {
                    id: detailModel
                    ListElement { name: "Clarity"; key: "clarity"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Texture"; key: "texture"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Sharpness"; key: "sharpness"; reverse: false; min: -100; max: 100 }
                }
                Repeater { model: detailModel; delegate: editSlider }

                // --- Histogram Group ---
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 140
                    Layout.topMargin: 5
                    spacing: 5
                    
                    SingleChannelHistogram {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        
                        channelName: "Red"
                        channelColor: "#e15050"
                        gridLineColor: imageEditorDialog.controlBorder
                        dangerColor: "#40ff0000"
                        textColor: imageEditorDialog.textColor
                        minimal: false
                        
                        histogramData: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["r"] || []) : []
                        clipCount: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["r_clip"] || 0) : 0
                        preClipCount: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["r_preclip"] || 0) : 0
                    }
                    
                    SingleChannelHistogram {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        
                        channelName: "Green"
                        channelColor: "#50e150"
                        gridLineColor: imageEditorDialog.controlBorder
                        dangerColor: "#40ff0000"
                        textColor: imageEditorDialog.textColor
                        minimal: false
                        
                        histogramData: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["g"] || []) : []
                        clipCount: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["g_clip"] || 0) : 0
                        preClipCount: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["g_preclip"] || 0) : 0
                    }

                    SingleChannelHistogram {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        
                        channelName: "Blue"
                        channelColor: "#5050e1"
                        gridLineColor: imageEditorDialog.controlBorder
                        dangerColor: "#40ff0000"
                        textColor: imageEditorDialog.textColor
                        minimal: false
                        
                        histogramData: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["b"] || []) : []
                        clipCount: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["b_clip"] || 0) : 0
                        preClipCount: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.histogramData ? (imageEditorDialog.uiStateRef.histogramData["b_preclip"] || 0) : 0
                    }
                }

                // Highlight State Indicators
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 2
                    spacing: 15
                    
                    Label {
                        visible: (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.highlightState && imageEditorDialog.uiStateRef.highlightState.headroom_pct > 0.001)
                        text: "📈 Headroom: " + (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.highlightState ? (imageEditorDialog.uiStateRef.highlightState.headroom_pct * 100).toFixed(1) : "0.0") + "%"
                        font.pixelSize: 10
                        color: "#50e150"  // Green - good, recoverable
                        opacity: 0.8
                    }
                    Label {
                        visible: (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.highlightState && imageEditorDialog.uiStateRef.highlightState.source_clipped_pct > 0.01)
                        text: "⚠ Clipped: " + (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.highlightState ? (imageEditorDialog.uiStateRef.highlightState.source_clipped_pct * 100).toFixed(1) : "0.0") + "%"
                        font.pixelSize: 10
                        color: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.highlightState && imageEditorDialog.uiStateRef.highlightState.source_clipped_pct > 0.05 ? "#e15050" : "#e1a050"  // Red if severe, orange if mild
                        opacity: 0.8
                    }
                    Item { Layout.fillWidth: true }  // Spacer
                }
            }

            // --- RIGHT COLUMN ---
            ColumnLayout { 
                Layout.fillWidth: true
                Layout.preferredWidth: (parent.width - 30) / 2
                Layout.alignment: Qt.AlignTop
                spacing: 15

                // --- Source Group ---
                Loader { 
                    sourceComponent: sectionHeader 
                    Layout.topMargin: 0 // Remove top margin for the very first item
                    onLoaded: item.text = "📸 Source"
                    visible: imageEditorDialog.uiStateRef ? imageEditorDialog.uiStateRef.hasRaw : false
                }
                Button {
                    text: (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.isRawActive) ? "RAW Loaded" : "Load RAW"
                    Layout.fillWidth: true
                    visible: imageEditorDialog.uiStateRef ? imageEditorDialog.uiStateRef.hasRaw : false
                    enabled: imageEditorDialog.uiStateRef ? !imageEditorDialog.uiStateRef.isRawActive : false
                    onClicked: {
                        if (imageEditorDialog.uiStateRef) imageEditorDialog.uiStateRef.enableRawEditing()
                        imageEditorDialog.updatePulse++
                    }
                }
                Label {
                    text: imageEditorDialog.uiStateRef ? imageEditorDialog.uiStateRef.saveBehaviorMessage : ""
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    font.pixelSize: 11
                    color: imageEditorDialog.textColor
                    opacity: 0.7
                    font.italic: true
                }
                Loader { 
                    sourceComponent: sectionSeparator 
                    visible: imageEditorDialog.uiStateRef ? imageEditorDialog.uiStateRef.hasRaw : false
                }

                // --- Color Group ---
                Loader { 
                    sourceComponent: sectionHeader 
                    Layout.topMargin: (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.hasRaw) ? 5 : 0 // Adjust logic if needed
                    onLoaded: item.text = "🎨 Color"
                }
                ListModel {
                    id: colorModel
                    ListElement { name: "Saturation"; key: "saturation"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Vibrance"; key: "vibrance"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Temp (Blue/Yel)"; key: "white_balance_by"; reverse: false; min: -100; max: 100 }
                    ListElement { name: "Tint (Grn/Mag)"; key: "white_balance_mg"; reverse: false; min: -100; max: 100 }
                }
                Repeater { model: colorModel; delegate: editSlider }
                
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Button {
                        id: autoWbButton
                        text: "Auto WB"
                        Layout.fillWidth: true
                        font.pixelSize: 12
                        onClicked: {
                            if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.auto_white_balance()
                            imageEditorDialog.updatePulse++
                        }
                    }
                    Button {
                        id: autoLevelsButton
                        text: "Auto Levels"
                        Layout.fillWidth: true
                        font.pixelSize: 12
                        onClicked: {
                            if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.auto_levels()
                            imageEditorDialog.updatePulse++
                        }
                    }
                }

                Loader { sourceComponent: sectionSeparator }

                // --- Effects Group ---
                Loader { 
                    sourceComponent: sectionHeader
                    onLoaded: item.text = "✨ Effects"
                }
                ListModel {
                    id: effectsModel
                    ListElement { name: "Vignette"; key: "vignette"; reverse: false; min: 0; max: 100 }
                }
                Repeater { model: effectsModel; delegate: editSlider }

                Button {
                    id: darkenModeButton
                    text: "Darken Background (K)"
                    Layout.fillWidth: true
                    font.pixelSize: 12
                    onClicked: {
                        if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.toggle_darken_mode()
                    }
                    contentItem: Text {
                        text: darkenModeButton.text
                        font: darkenModeButton.font
                        color: (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.isDarkening) ? "white" : imageEditorDialog.textColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        color: (imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.isDarkening) ? imageEditorDialog.accentColor : (darkenModeButton.down ? "#40ffffff" : "#20ffffff")
                        radius: 4
                        border.color: darkenModeButton.hovered ? "#60ffffff" : "transparent"
                    }
                }

                Loader { sourceComponent: sectionSeparator }

                // --- Transform Group ---
                Loader { 
                    sourceComponent: sectionHeader
                    onLoaded: item.text = "🔄 Transform"
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 15
                    Label { 
                        text: "Rotation" 
                        color: imageEditorDialog.textColor 
                        font.pixelSize: 14
                    }
                    Item { Layout.fillWidth: true } // Spacer
                    Button { 
                        text: "↶ -90°" 
                        onClicked: { if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.rotate_image_ccw() }
                        Layout.preferredWidth: 80
                    }
                    Button { 
                        text: "↷ +90°" 
                        onClicked: { if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.rotate_image_cw() }
                        Layout.preferredWidth: 80
                    }
                }

                // --- Action Buttons ---
                Item { Layout.fillHeight: true; Layout.minimumHeight: 30 }
                
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    // Reset (Tertiary)
                    Button { 
                        id: resetButton
                        text: "Reset"
                        flat: true
                        Layout.preferredWidth: 80
                        Material.foreground: imageEditorDialog.textColor
                        onClicked: {
                            if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.reset_edit_parameters()
                            imageEditorDialog.updatePulse++
                        }
                        background: Rectangle {
                            color: resetButton.down ? "#20ffffff" : "transparent"
                            radius: 4
                            border.color: resetButton.hovered ? "#40ffffff" : "transparent"
                        }
                    }

                    Item { Layout.fillWidth: true } // Spacer

                    // Close (Secondary)
                    Button { 
                        id: closeEditorButton
                        text: "Close"
                        Layout.preferredWidth: 100
                        onClicked: { 
                            if (imageEditorDialog.uiStateRef) imageEditorDialog.uiStateRef.isEditorOpen = false
                        }
                        contentItem: Text {
                            text: closeEditorButton.text
                            font: closeEditorButton.font
                            opacity: closeEditorButton.enabled ? 1.0 : 0.3
                            color: imageEditorDialog.textColor
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            color: closeEditorButton.down ? "#40ffffff" : "#20ffffff"
                            radius: 4
                            border.color: closeEditorButton.hovered ? "#60ffffff" : "transparent"
                        }
                    }

                    // Save (Primary)
                    Button { 
                        id: saveEditorButton
                        text: imageEditorDialog.uiStateRef && imageEditorDialog.uiStateRef.isSaving ? "Saving..." : "Save"
                        Layout.preferredWidth: 100
                        highlighted: true
                        enabled: imageEditorDialog.uiStateRef ? !imageEditorDialog.uiStateRef.isSaving : true
                        Material.background: imageEditorDialog.accentColor
                        onClicked: {
                            if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.save_edited_image()
                            // Note: Editor closes automatically via _on_save_finished callback
                        }
                        background: Rectangle {
                            color: saveEditorButton.enabled ? (saveEditorButton.down ? Qt.darker(imageEditorDialog.accentColor, 1.1) : imageEditorDialog.accentColor) : Qt.darker(imageEditorDialog.accentColor, 1.5)
                            radius: 4
                            // Subtle shadow simulation
                            layer.enabled: true
                        }
                    }
                }
            }
        }
    }

    Component {
        id: editSlider
        RowLayout {
            id: sliderRow
            required property string name
            required property string key
            required property bool reverse
            required property real min
            required property real max

            Layout.fillWidth: true
            spacing: 15
            
            property bool isReversed: reverse
            property real minVal: min
            property real maxVal: max
            
            // Label
            Text {
                text: sliderRow.name
                color: imageEditorDialog.textColor
                font.pixelSize: 13
                font.weight: Font.Medium
                Layout.preferredWidth: 90
                Layout.alignment: Qt.AlignVCenter
                elide: Text.ElideRight
            }
            
            // Slider
            Slider {
                id: slider
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                from: sliderRow.minVal
                to: sliderRow.maxVal
                stepSize: 1
                
                property real backendValue: {
                    var val = imageEditorDialog.getBackendValue(sliderRow.key) * sliderRow.maxVal
                    return sliderRow.isReversed ? -val : val
                }
                
                // Auto-sync visual slider with backend changes when not dragging
                Binding {
                    target: slider
                    property: "value"
                    value: slider.backendValue
                    when: !slider.pressed && !slider.isResetting
                }

                property real _pendingValue: 0
                property real _lastSentValue: 0
                Timer {
                    id: sendTimer
                    interval: 16 // ~60fps throttle
                    repeat: true
                    onTriggered: {
                        if (Math.abs(slider._pendingValue - slider._lastSentValue) > 0.001) {
                            var sendValue = sliderRow.isReversed ? -slider._pendingValue : slider._pendingValue
                            if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.set_edit_parameter(sliderRow.key, sendValue / sliderRow.maxVal)
                            slider._lastSentValue = slider._pendingValue
                        }
                    }
                }
                
                // Double-click reset using TapHandler (coexists with Slider drag)
                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    gesturePolicy: TapHandler.DragThreshold
                    onDoubleTapped: {
                        if (!slider.isResetting)
                            slider.triggerReset()
                    }
                }

                property bool isResetting: false
                
                // Timer to handle reset state duration
                Timer {
                    id: resetTimer
                    interval: 100 // Lock for 100ms to prevent accidental drags during reset
                    repeat: false
                    onTriggered: {
                        slider.isResetting = false
                    }
                }
                
                function triggerReset() {
                    slider.isResetting = true
                    sendTimer.stop()
                    if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.set_edit_parameter(sliderRow.key, 0.0)
                    slider.value = 0.0
                    _pendingValue = 0.0
                    slider._lastSentValue = 0.0
                    imageEditorDialog.updatePulse++
                    resetTimer.restart()
                }

                onPressedChanged: {
                    if (pressed) {
                        imageEditorDialog.slidersPressedCount++
                        
                        // Initialize drag logic only if not resetting
                        if (!slider.isResetting) {
                            _pendingValue = value
                            slider._lastSentValue = value
                            if (!sendTimer.running) sendTimer.start()
                        }
                    } else {
                        imageEditorDialog.slidersPressedCount--
                        sendTimer.stop()
                        
                        if (slider.isResetting) {
                             // Force backend to 0 on release (redundant but safe)
                             if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.set_edit_parameter(sliderRow.key, 0.0)
                        } else {
                             // Send final value immediately
                             var sendValue = sliderRow.isReversed ? -value : value
                             if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.set_edit_parameter(sliderRow.key, sendValue / sliderRow.maxVal)
                        }
                        
                        if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.update_histogram()
                    }
                }
                
                onMoved: {
                    if (slider.isResetting) return
                    _pendingValue = value
                    if (!sendTimer.running) sendTimer.start()
                }

                // Smooth transition for value changes from backend
                Behavior on value {
                    enabled: !slider.pressed && !slider.isResetting
                    NumberAnimation { duration: 200; easing.type: Easing.OutQuad }
                }
                
                background: Item {
                    x: slider.leftPadding
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    width: slider.availableWidth
                    height: 6
                    
                    // Track Background
                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: imageEditorDialog.controlBg
                        border.color: imageEditorDialog.controlBorder
                        border.width: 1
                    }

                    // Fill Indicator (From 0/Center to Value)
                    Rectangle {
                        id: fillRect
                        property real range: slider.to - slider.from
                        // Determine anchor point (0 if within range, else min or max)
                        property real anchorVal: Math.max(slider.from, Math.min(slider.to, 0))
                        property real anchorPos: (anchorVal - slider.from) / range
                        
                        x: Math.min(slider.visualPosition, anchorPos) * parent.width
                        width: Math.abs(slider.visualPosition - anchorPos) * parent.width
                        height: parent.height
                        radius: 3
                        color: imageEditorDialog.accentColor
                        opacity: 0.6 // Reduced opacity as requested
                        
                        Behavior on width { NumberAnimation { duration: 100 } }
                        Behavior on x { NumberAnimation { duration: 100 } }
                    }
                }

                handle: Rectangle {
                     x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                     y: slider.topPadding + slider.availableHeight / 2 - height / 2
                     width: 12
                     height: 12
                     radius: 6
                     color: slider.pressed ? imageEditorDialog.accentColor : "white"
                     border.color: slider.pressed ? "white" : imageEditorDialog.accentColor
                     border.width: 2
                     
                     // Glow/Scale effect on hover
                     scale: hoverHandler.hovered || slider.pressed ? 1.3 : 1.0
                     Behavior on scale { NumberAnimation { duration: 150; easing.type: Easing.OutBack } }
                     Behavior on color { ColorAnimation { duration: 150 } }

                     HoverHandler {
                          id: hoverHandler
                     }
                }
            }

            // Refined SpinBox
            SpinBox {
                id: valueInput
                from: sliderRow.minVal
                to: sliderRow.maxVal
                stepSize: 1
                editable: true
                Layout.preferredWidth: 80
                Layout.alignment: Qt.AlignVCenter
                
                value: sliderRow.isReversed ? -slider.value : slider.value
                
                onValueModified: {
                     var val = value
                     var sendValue = sliderRow.isReversed ? -val : val
                     if (imageEditorDialog.controllerRef) imageEditorDialog.controllerRef.set_edit_parameter(sliderRow.key, sendValue / sliderRow.maxVal)
                     imageEditorDialog.updatePulse++ 
                }

                contentItem: TextInput {
                    z: 2
                    text: valueInput.displayText
                    font.pixelSize: 12
                    font.family: valueInput.font.family
                    color: imageEditorDialog.textColor
                    selectionColor: imageEditorDialog.accentColor
                    selectedTextColor: "#ffffff"
                    horizontalAlignment: Qt.AlignHCenter
                    verticalAlignment: Qt.AlignVCenter
                    readOnly: !valueInput.editable
                    validator: valueInput.validator
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    
                    // Highlight on focus
                    onActiveFocusChanged: {
                        if(activeFocus) valueInputBackground.border.color = imageEditorDialog.accentColor
                        else valueInputBackground.border.color = imageEditorDialog.controlBorder
                    }
                }

                up.indicator: Item {
                    x: valueInput.mirrored ? 0 : parent.width - width
                    height: parent.height
                    width: 16 // Smaller button
                    
                    Rectangle {
                        anchors.centerIn: parent
                        width: 16; height: 16
                        radius: 2
                        color: valueInput.up.pressed ? imageEditorDialog.accentColor : (valueInput.up.hovered ? Qt.lighter(imageEditorDialog.controlBg, 1.5) : "transparent")
                        
                        Text {
                            text: "+"
                            font.pixelSize: 12
                            anchors.centerIn: parent
                            color: valueInput.up.pressed ? "white" : imageEditorDialog.textColor
                        }
                    }
                }

                down.indicator: Item {
                    x: valueInput.mirrored ? parent.width - width : 0
                    height: parent.height
                    width: 16 // Smaller button
                    
                    Rectangle {
                        anchors.centerIn: parent
                        width: 16; height: 16
                        radius: 2
                        color: valueInput.down.pressed ? imageEditorDialog.accentColor : (valueInput.down.hovered ? Qt.lighter(imageEditorDialog.controlBg, 1.5) : "transparent")
                        
                        Text {
                            text: "-"
                            font.pixelSize: 12
                            anchors.centerIn: parent
                            color: valueInput.down.pressed ? "white" : imageEditorDialog.textColor
                        }
                    }
                }

                background: Rectangle {
                    id: valueInputBackground
                    implicitWidth: 80
                    color: "transparent"
                    border.color: imageEditorDialog.controlBorder
                    border.width: 1
                    radius: 4
                    
                    Behavior on border.color { ColorAnimation { duration: 150 } }
                }
            }
        }
    }
}
