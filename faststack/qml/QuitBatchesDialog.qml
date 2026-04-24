import QtQuick 2.15
import QtQuick.Controls 2.15

Dialog {
    id: quitBatchesDialog
    title: "Quit with Batches?"
    modal: true
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape
    width: 450
    height: 250

    property int batchCount: 0
    property color backgroundColor: "#1e1e1e"
    property color textColor: "white"
    property var controllerRef: null
    signal quitConfirmed()

    background: Rectangle {
        color: quitBatchesDialog.backgroundColor
        border.color: "#404040"
        border.width: 1
        radius: 4
    }

    contentItem: Column {
        spacing: 20
        padding: 20

        Label {
            text: `You have ${quitBatchesDialog.batchCount} image${quitBatchesDialog.batchCount === 1 ? '' : 's'} selected in batches.`
            wrapMode: Text.WordWrap
            width: parent.width - parent.padding * 2
            color: quitBatchesDialog.textColor
            font.pixelSize: 14
        }

        Label {
            text: "Batches are not saved after FastStack quits. Quit anyway?"
            wrapMode: Text.WordWrap
            width: parent.width - parent.padding * 2
            color: quitBatchesDialog.textColor
            font.pixelSize: 14
        }

        Row {
            spacing: 10
            anchors.horizontalCenter: parent.horizontalCenter

            Button {
                id: cancelQuitButton
                text: "Cancel"
                onClicked: quitBatchesDialog.close()
                background: Rectangle {
                    color: cancelQuitButton.down ? "#555555" : (cancelQuitButton.hovered ? "#666666" : "#444444")
                    radius: 4
                }
                contentItem: Text {
                    text: cancelQuitButton.text
                    color: quitBatchesDialog.textColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Button {
                id: quitAnywayButton
                text: "Quit Anyway"
                onClicked: {
                    quitBatchesDialog.close()
                    quitBatchesDialog.quitConfirmed()
                }
                background: Rectangle {
                    color: quitAnywayButton.down ? "#cc0000" : (quitAnywayButton.hovered ? "#ff0000" : "#aa0000")
                    radius: 4
                }
                contentItem: Text {
                    text: quitAnywayButton.text
                    color: quitBatchesDialog.textColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.bold: true
                }
            }
        }
    }

    onOpened: {
        if (quitBatchesDialog.controllerRef) {
            quitBatchesDialog.controllerRef.dialog_opened()
        }
    }

    onClosed: {
        if (quitBatchesDialog.controllerRef) {
            quitBatchesDialog.controllerRef.dialog_closed()
        }
    }
}
