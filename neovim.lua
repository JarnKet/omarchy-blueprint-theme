-- Blueprint: Omarchy's generated aether palette, marked as a light theme.
return {
  {
    "bjarneo/aether.nvim",
    -- aether takes the palette but never sets 'background'; tell Neovim
    -- (and every plugin that asks) this is a light theme.
    init = function()
      vim.o.background = "light"
    end,
    branch = "v3",
    name = "aether",
    priority = 1000,
    opts = {
      colors = {
        bg = "#ffffff",
        dark_bg = "#f7f7f8",
        darker_bg = "#eeeff1",
        lighter_bg = "#ececef",

        fg = "#18181b",
        dark_fg = "#a1a1aa",
        light_fg = "#3f3f46",
        bright_fg = "#000000",
        muted = "#5f5f68",

        red = "#c2372b",
        yellow = "#8a5d00",
        orange = "#c2410c",
        green = "#16794a",
        cyan = "#0e7490",
        blue = "#104bff",
        magenta = "#6a4cf5",
        brown = "#7c4a1e",

        bright_red = "#a3291f",
        bright_yellow = "#704b00",
        bright_green = "#11643c",
        bright_cyan = "#0b5e75",
        bright_blue = "#0a3ee0",
        bright_magenta = "#5232d8",

        accent = "#104bff",
        cursor = "#000000",
        foreground = "#18181b",
        background = "#ffffff",
        selection = "#d6e1ff",
        selection_foreground = "#000000",
        selection_background = "#d6e1ff",
      },
    },
  },
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "aether",
    },
  },
}
