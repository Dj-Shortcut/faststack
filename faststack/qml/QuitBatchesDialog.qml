import QtQuick 2.15
import QtQuick.Controls 2.15

Dialog {
    id: quitBatchesDialog
    title: "Quit with Batches?"
    modal: true
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape
    width: Math.min(maxDialogWidth, parent ? parent.width * 0.9 : maxDialogWidth)
    implicitHeight: quitDialogContent.implicitHeight

    property int batchCount: 0
    property int maxDialogWidth: 450
    property bool darkTheme: true
    property color backgroundColor: "#1e1e1e"
    property color textColor: "white"
    property color frameBorderColor: darkTheme ? "#404040" : "#d0d0d0"
    property color cancelBgColor: darkTheme ? "#444444" : "#f0f0f0"
    property color cancelHoverColor: darkTheme ? "#666666" : "#e0e0e0"
    property color cancelPressedColor: darkTheme ? "#555555" : "#d0d0d0"
    property color quitBgColor: "#aa0000"
    property color quitHoverColor: "#ff0000"
    property color quitPressedColor: "#cc0000"
    property var controllerRef: null
    signal quitConfirmed()

    background: Rectangle {
        color: quitBatchesDialog.backgroundColor
        border.color: quitBatchesDialog.frameBorderColor
        border.width: 1
        radius: 4
    }

    contentItem: Column {
        id: quitDialogContent
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
                    color: cancelQuitButton.down ? quitBatchesDialog.cancelPressedColor : (cancelQuitButton.hovered ? quitBatchesDialog.cancelHoverColor : quitBatchesDialog.cancelBgColor)
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
                    color: quitAnywayButton.down ? quitBatchesDialog.quitPressedColor : (quitAnywayButton.hovered ? quitBatchesDialog.quitHoverColor : quitBatchesDialog.quitBgColor)
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
