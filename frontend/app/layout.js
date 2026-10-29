import "./globals.css"

export const metadata = {
  title: "DreamTalk",
  description: "A thoughtful AI companion"
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
