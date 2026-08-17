import React from "react";
import { Box, Typography } from "@mui/material";
import "./CategoryBar.css";

const categories = [
  "Women",
  "Juniors",
  "Men",
  "Kids",
  "Shoes",
  "Handbags",
  "Accessories"
];

const CategoryBar = () => {
  return (
    <Box className="category-bar">
      {categories.map((category, index) => (
        <Typography key={index} className="category-item">
          {category}
        </Typography>
      ))}
    </Box>
  );
};

export default CategoryBar;
