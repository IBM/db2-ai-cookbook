import React from "react";
import { Box, Typography, Rating, Stack } from "@mui/material";
import "./ShoeCard.css";
import { useNavigate } from "react-router-dom";

interface ShoeCardProps {
  image: string;
  PRODUCT_NAME?: string;
  PRICE: number;
  RATING?: number;
  COLORS?: string[];
  id?: any;
  COLOR?: string;
  BRAND?: string;
  CLASS?: string;
  TYPE?: string;
  MATERIAL?: string;
  SIZE?: number;
  SKU?: string;
  CITY?: string;
  STORE_ID?: number;
  DESCRIPTION: string;
}

const ShoeCard: React.FC<ShoeCardProps> = ({
  image,
  PRODUCT_NAME,
  DESCRIPTION,
  PRICE,
  RATING,
  COLORS,
  id,
  COLOR,
}) => {
  const navigate = useNavigate();

  return (
    <Box
      className="shoe-card"
      onClick={() => navigate(`/shoe/${id}`)}
      sx={{
        cursor: "pointer",
        transition: "transform 0.2s",
        "&:hover": { transform: "scale(1.02)" },
      }}
    >
      <Box component="img" src={image} alt="shoe" className="shoe-image" />
      <Typography variant="h6" sx={{ fontWeight: 600, mt: 2 }}>
        {PRODUCT_NAME}
      </Typography>
      <Typography
        variant="body2"
        sx={{ color: "var(--text-muted)", mt: 1, textAlign: "center" }}
      >
        {DESCRIPTION}
      </Typography>
      <Typography
        variant="h6"
        sx={{ fontWeight: 700, color: "var(--accent-color)", mt: 1 }}
      >
        ${PRICE.toLocaleString()}
      </Typography>
      <Rating name="rating" value={RATING} readOnly sx={{ mt: 1 }} />
      {COLORS && (
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          {COLORS.map((color, index) => (
            <Box
              key={index}
              sx={{
                backgroundColor: color,
                width: 24,
                height: 24,
                borderRadius: "50%",
                border: "1px solid #ccc",
              }}
            />
          ))}
        </Stack>
      )}
    </Box>
  );
};

export default ShoeCard;
