import React, { useState } from "react";
import {
  Box,
  Typography,
  Checkbox,
  Divider,
  TextField,
  InputAdornment,
  Drawer,
  IconButton,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import MenuIcon from "@mui/icons-material/Menu";
import "./SideNav.css";

const filters = ["Just For You", "New Arrivals", "Sale"];
const categories = ["Athletic", "Casual"];
const brands = ["Aetrex", "ALDO", "Alex Marie"];

const SidebarContent = () => (
  <Box className="sidebar-content">
    {/* Breadcrumb */}
    <Typography className="breadcrumb">
      <b>Shoes</b> / <b>Women's Shoes</b> / <b>Sneakers</b>
    </Typography>

    {/* Filter Section */}
    {filters.map((item, index) => (
      <React.Fragment key={index}>
        <Box className="filter-item">
          <Checkbox
            size="small"
            className="checkbox"
            sx={{
              "&.Mui-checked": { color: "var(--accent-color)" },
            }}
          />
          <Typography variant="body2">{item}</Typography>
        </Box>
        <Divider className="divider" />
      </React.Fragment>
    ))}

    {/* Category Section */}
    <Typography className="category-title" variant="subtitle1">
      Category
    </Typography>
    {categories.map((cat, index) => (
      <Typography key={index} variant="body2" className="category-item">
        {cat}
      </Typography>
    ))}

    <Divider className="divider" />

    {/* Brand Section */}
    <Typography className="brand-title" variant="subtitle1">
      Brand
    </Typography>
    <TextField
      fullWidth
      variant="standard"
      placeholder="Search by brand..."
      className="brand-search"
      InputProps={{
        disableUnderline: true,
        startAdornment: (
          <InputAdornment position="start">
            <SearchIcon className="search-icon" fontSize="small" />
          </InputAdornment>
        ),
        sx: { fontSize: "0.9rem", paddingY: 1 },
      }}
      inputProps={{ style: { color: "var(--text-color)" } }}
    />

    {brands.map((brand, index) => (
      <Box key={index} className="brand-item">
        <Checkbox
          size="small"
          className="checkbox"
          sx={{
            "&.Mui-checked": { color: "var(--accent-color)" },
          }}
        />
        <Typography variant="body2">{brand}</Typography>
      </Box>
    ))}
  </Box>
);

const SideNav: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));
  const [open, setOpen] = useState(false);

  return (
    <>
      {
        //   isMobile ? (
        //     <>
        //       {/* Mobile Menu Toggle Button */}
        //       <IconButton
        //         onClick={() => setOpen((prev) => !prev)}
        //         className="mobile-menu-button"
        //       >
        //         <MenuIcon />
        //       </IconButton>

        //       {/* Drawer for Mobile */}
        //       <Drawer
        //         open={open}
        //         onClose={() => setOpen(false)}
        //         anchor="left"
        //         ModalProps={{
        //           keepMounted: true,
        //         }}
        //         sx={{
        //           "& .MuiDrawer-paper": {
        //             backgroundColor: "var(--bg-color)",
        //             color: "var(--text-color)",
        //           },
        //         }}
        //       >
        //         <SidebarContent />
        //       </Drawer>
        //     </>
        //   )
        //   : (
        <Box className="sidebar">
          <SidebarContent />
        </Box>
        //   )
      }
    </>
  );
};

export default SideNav;
