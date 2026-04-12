import QtQuick
import QtQuick.Window
import QtQuick.Layouts 1.15

Window {
    id: histogramWindow
    title: "RGB Histogram"
    width: 750
    height: 450
    minimumWidth: 100
    minimumHeight: 50
    property var uiStateRef: typeof uiState !== "undefined" ? uiState : null
    property var controllerRef: typeof controller !== "undefined" ? controller : null
    visible: histogramWindow.uiStateRef ? histogramWindow.uiStateRef.isHistogramVisible : false

    FocusScope {
        id: histogramKeyScope
        anchors.fill: parent
        focus: histogramWindow.visible

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_H && histogramWindow.controllerRef) {
                histogramWindow.controllerRef.toggle_histogram()
                event.accepted = true
            } else if (histogramWindow.controllerRef) {
                // Forward unhandled keys (e.g. arrow keys) to controller
                histogramWindow.controllerRef.handle_key_from_histogram(event.key, event.modifiers, event.text)
                event.accepted = true
            }
        }
    }
    
    Connections {
        target: histogramWindow.uiStateRef
        function onCurrentImageSourceChanged() {
            if (histogramWindow.visible && histogramWindow.controllerRef) {
                histogramWindow.controllerRef.update_histogram()
            }
        }
    }

    onVisibleChanged: {
        if (visible && histogramWindow.controllerRef) {
            histogramKeyScope.forceActiveFocus()
            histogramWindow.controllerRef.update_histogram()
        }
    }

    // --- Injected Properties ---
    property color windowBackgroundColor: "#f4f4f4"
    property color primaryTextColor: "#222222"
    property color gridLineColor: "#dcdcdc"
    property color dangerColor: Qt.rgba(1, 0, 0, 0.25)

    color: windowBackgroundColor

    RowLayout {
        anchors.fill: parent
        anchors.margins: histogramWindow.width > 200 ? 15 : 2
        spacing: histogramWindow.width > 200 ? 15 : 2

        SingleChannelHistogram {
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            channelName: "Red"
            channelColor: "#e15050"
            gridLineColor: histogramWindow.gridLineColor
            dangerColor: histogramWindow.dangerColor
            textColor: histogramWindow.primaryTextColor
            
            histogramData: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["r"] || []) : []
            clipCount: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["r_clip"] || 0) : 0
            preClipCount: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["r_preclip"] || 0) : 0
        }
        
        SingleChannelHistogram {
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            channelName: "Green"
            channelColor: "#50e150"
            gridLineColor: histogramWindow.gridLineColor
            dangerColor: histogramWindow.dangerColor
            textColor: histogramWindow.primaryTextColor
            
            histogramData: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["g"] || []) : []
            clipCount: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["g_clip"] || 0) : 0
            preClipCount: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["g_preclip"] || 0) : 0
        }

        SingleChannelHistogram {
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            channelName: "Blue"
            channelColor: "#5050e1"
            gridLineColor: histogramWindow.gridLineColor
            dangerColor: histogramWindow.dangerColor
            textColor: histogramWindow.primaryTextColor
            
            histogramData: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["b"] || []) : []
            clipCount: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["b_clip"] || 0) : 0
            preClipCount: histogramWindow.uiStateRef && histogramWindow.uiStateRef.histogramData ? (histogramWindow.uiStateRef.histogramData["b_preclip"] || 0) : 0
        }
    }
}
