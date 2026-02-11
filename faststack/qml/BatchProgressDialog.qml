import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15

Dialog {
    id: batchProgressDialog
    title: "Batch Auto Levels"
    modal: true
    standardButtons: Dialog.NoButton
    closePolicy: Popup.NoAutoClose
    width: 400
    height: 180

    property color backgroundColor: "#1e1e1e"
    property color textColor: "white"

    background: Rectangle {
        color: batchProgressDialog.backgroundColor
        border.color: "#404040"
        border.width: 1
        radius: 4
    }

    contentItem: Column {
        spacing: 16
        padding: 20

        Label {
            id: statusLabel
            text: {
                if (!uiState) return ""
                var current = uiState.batchAutoLevelsCurrent
                var total = uiState.batchAutoLevelsTotal
                return `Processing image ${current} of ${total}...`
            }
            color: batchProgressDialog.textColor
            font.pixelSize: 14
            width: parent.width - parent.padding * 2
        }

        ProgressBar {
            id: progressBar
            width: parent.width - parent.padding * 2
            from: 0
            to: uiState ? uiState.batchAutoLevelsTotal : 1
            value: uiState ? uiState.batchAutoLevelsCurrent : 0

            background: Rectangle {
                implicitHeight: 12
                color: "#333333"
                radius: 6
            }
            contentItem: Item {
                implicitHeight: 12
                Rectangle {
                    width: progressBar.visualPosition * parent.width
                    height: parent.height
                    radius: 6
                    color: "#4CAF50"
                }
            }
        }

        Button {
            text: "Cancel"
            anchors.horizontalCenter: parent.horizontalCenter
            onClicked: {
                if (uiState) uiState.cancelBatchAutoLevels()
            }
            background: Rectangle {
                color: parent.pressed ? "#555555" : (parent.hovered ? "#666666" : "#444444")
                radius: 4
            }
            contentItem: Text {
                text: parent.text
                color: batchProgressDialog.textColor
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Connections {
        target: uiState
        function onBatchAutoLevelsActiveChanged() {
            if (uiState && uiState.batchAutoLevelsActive) {
                batchProgressDialog.open()
            } else {
                batchProgressDialog.close()
            }
        }
    }
}
