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
    property var uiStateRef: typeof uiState !== "undefined" ? uiState : null

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
                if (!batchProgressDialog.uiStateRef) return ""
                var current = batchProgressDialog.uiStateRef.batchAutoLevelsCurrent
                var total = batchProgressDialog.uiStateRef.batchAutoLevelsTotal
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
            to: batchProgressDialog.uiStateRef ? batchProgressDialog.uiStateRef.batchAutoLevelsTotal : 1
            value: batchProgressDialog.uiStateRef ? batchProgressDialog.uiStateRef.batchAutoLevelsCurrent : 0

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
            id: cancelButton
            text: "Cancel"
            anchors.horizontalCenter: parent.horizontalCenter
            onClicked: {
                if (batchProgressDialog.uiStateRef) batchProgressDialog.uiStateRef.cancelBatchAutoLevels()
            }
            background: Rectangle {
                color: cancelButton.down ? "#555555" : (cancelButton.hovered ? "#666666" : "#444444")
                radius: 4
            }
            contentItem: Text {
                text: cancelButton.text
                color: batchProgressDialog.textColor
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Connections {
        target: batchProgressDialog.uiStateRef
        function onBatchAutoLevelsActiveChanged() {
            if (batchProgressDialog.uiStateRef && batchProgressDialog.uiStateRef.batchAutoLevelsActive) {
                batchProgressDialog.open()
            } else {
                batchProgressDialog.close()
            }
        }
    }
}
