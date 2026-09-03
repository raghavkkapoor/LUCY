using System.Windows;
using System.Windows.Input;
using System;
using System.Threading.Tasks;

namespace TransparentRectangleWpf;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        MouseLeftButtonDown += Window_MouseLeftButtonDown;
    }

    private void Window_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource is not System.Windows.Controls.TextBox &&
            e.OriginalSource is not System.Windows.Controls.Button)
        {
            DragMove();
        }
    }

    private void ExitButton_Click(object sender, RoutedEventArgs e)
    {
        Close();
    }

    private void InputBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && Keyboard.Modifiers == ModifierKeys.None)
        {
            e.Handled = true;
            SendToGeminiAsync();
        }
    }

    private void SendButton_Click(object sender, RoutedEventArgs e)
    {
        SendToGeminiAsync();
    }

    private async void SendToGeminiAsync()
    {
        var request = InputBox.Text.Trim();
        if (!SendButton.IsEnabled || string.IsNullOrWhiteSpace(request))
            return;

        SendButton.IsEnabled = false;
        InputBox.IsEnabled = false;
        ResponseBox.Text = "Waiting for Gemini...";

        try
        {
            ResponseBox.Text = await GeminiClient.SendAsync(request);
        }
        catch (Exception ex)
        {
            ResponseBox.Text = $"ERROR: {ex.Message}";
        }
        finally
        {
            InputBox.IsEnabled = true;
            SendButton.IsEnabled = true;
            InputBox.Focus();
        }
    }
}
