// Trusted repository template. All untrusted strings are text; never eval/include.
#let resume = json("data.json")
#set document(title: "简历", author: "", date: none)
#set page(paper: "a4", margin: (x: 18mm, y: 16mm), numbering: none)
#set text(font: "Noto Sans CJK SC", fallback: false, size: 10.5pt,
          top-edge: "ascender", bottom-edge: "descender",
          lang: "zh", region: "CN", hyphenate: false, ligatures: false, overhang: false)
// Fixed half-em gutter keeps CJK punctuation advance boxes inside the content bounds.
#show: body => pad(right: 5.25pt, body)
#set par(justify: false, leading: 0.6em, spacing: 0.45em)
#let contacts() = layout(size => {
  let line-text = ""
  for item in resume.at("contacts", default: ()) {
    let candidate = if line-text == "" { item } else { line-text + " · " + item }
    if line-text != "" and measure(text(candidate)).width > size.width {
      text(line-text)
      linebreak()
      line-text = item
    } else { line-text = candidate }
  }
  if line-text != "" { text(line-text) }
})
#if resume.at("photo", default: false) {
  grid(columns: (1fr, auto), column-gutter: 10pt, align: (left, right), [
    #text(size: 20pt, weight: "bold", resume.name)
    #parbreak()
    #contacts()
  ], image("photo.jpg", width: 20mm, height: 26mm, fit: "cover"))
} else {
  text(size: 20pt, weight: "bold", resume.name)
  if resume.at("contacts", default: ()).len() > 0 {
    parbreak()
    contacts()
  }
}
#v(5pt)
#for section in resume.sections {
  block(above: 7pt, below: 4pt)[
    #text(size: 12pt, weight: "bold", section.heading)
    #v(2pt)
    #line(length: 100%, stroke: 0.4pt)
  ]
  for item in section.items {
    if item.at("structured", default: false) {
      block(above: 3pt, below: 5pt)[
        #grid(columns: (1fr, auto), column-gutter: 8pt, align: (left, right), [
          #text(weight: "bold", item.title)#if item.subtitle != "" { h(8pt); text(item.subtitle) }
        ], text(size: 10.5pt, item.period))
        #for line-text in item.body {
          block(above: 2pt, below: 1pt, inset: (left: 7pt))[
            #set par(hanging-indent: 7pt)
            #box(width: 7pt, circle(radius: 1pt, fill: black))#text(line-text)
          ]
        }
      ]
    } else if item.kind == "bullet" {
      block(above: 0pt, below: 4pt, inset: (left: 7pt))[
        #set par(hanging-indent: 7pt)
        #box(width: 7pt, circle(radius: 1.2pt, fill: black))#text(item.text)
      ]
    } else {
      block(above: 0pt, below: 4pt)[#text(item.text)]
    }
  }
}
