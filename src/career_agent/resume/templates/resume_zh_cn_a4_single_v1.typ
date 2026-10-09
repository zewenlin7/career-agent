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
#text(size: 20pt, weight: "bold", resume.name)
#v(5pt)
#for section in resume.sections {
  block(above: 7pt, below: 4pt)[
    #text(size: 12pt, weight: "bold", section.heading)
    #v(2pt)
    #line(length: 100%, stroke: 0.4pt)
  ]
  for item in section.items {
    if item.kind == "bullet" {
      block(above: 0pt, below: 4pt, inset: (left: 7pt))[
        #set par(hanging-indent: 7pt)
        #box(width: 7pt, circle(radius: 1.2pt, fill: black))#text(item.text)
      ]
    } else {
      block(above: 0pt, below: 4pt)[#text(item.text)]
    }
  }
}
