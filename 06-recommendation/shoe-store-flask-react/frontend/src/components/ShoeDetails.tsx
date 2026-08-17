import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Button,
  Rating,
  IconButton,
  Skeleton,
} from "@mui/material";
import { useParams } from "react-router-dom";
import axios from "axios";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";
import DefaultShoeImage from "../assets/defaultShoe.avif";
import Shoe1Red from "../assets/shoe1Red.avif";
import Shoe1White from "../assets/shoe1White.avif";
import Shoe1Black from "../assets/shoe1Black.avif";
import Shoe2Yellow from "../assets/shoe2Yellow.avif";
import Shoe3Black from "../assets/shoe3Black.avif";
import Shoe4Black from "../assets/shoe4Brown.avif";
import Shoe5White from "../assets/greenSimilarShoe1.png";
import Shoe6White from "../assets/shoe5Grey.png";


import "./ShoeDetails.css";
import SimilarProducts from "./SimilarProducts";

const imageMap: Record<string, string> = {
  "ZEN-5999_red": Shoe1Red,
  "ZEN-5999_white": Shoe1White,
  "ZEN-5999_black": Shoe1Black,

  "RUN-4723_yellow": Shoe2Yellow,

  "ZEN-8968_black": Shoe3Black,
  "ZEN-8968_white": Shoe6White,
  "RUN-7569_black": Shoe4Black,

  "LOO-1505_white": Shoe5White,
  "RUN-1083_white": Shoe6White
};


const colorHexToNameMap: Record<string, string> = {
  "#d90000": "red",
  "#f0f0f0": "white",
  "#ffffff": "white",
  "#000000": "black",
  "#f5c514": "yellow",
  "#e2cbb5": "white",
};




interface Shoe {
  SKU: string;
  id: number;
  PRODUCT_NAME: string;
  DESCRIPTION: string;
  PRICE: number;
  RATING: number;
  COLOR_SIZES: { color: string; sizes: number[] }[];
  image: string;
  AVAILABLE_SIZES?: number[];
}

interface Product {
  SKU: string;
  PRODUCT_NAME: string;
  PRICE: number;
  BRAND: string;
  COLOR: string;
  RATING: number;
}

const ShoeDetails: React.FC = () => {
  const { id } = useParams();
  const [shoe, setShoe] = useState<Shoe | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [selectedSize, setSelectedSize] = useState<number | null>(null);
  const [selectedColor, setSelectedColor] = useState<string>("");
  const [currentImage, setCurrentImage] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const allSizes = Array.from(
    { length: 13 },
    (_, i) => +(5 + i * 0.5).toFixed(1)
  );

  useEffect(() => {
    if (id) {
      axios
        .get(`/api/products/${id}`)
        .then((res) => {
          const shoeData = res.data;
          setShoe(shoeData);
          const defaultColor = shoeData.COLOR_SIZES[0].color;
          setSelectedColor(defaultColor);
          setSelectedSize(shoeData.COLOR_SIZES[0].sizes[0]);

          const colorKey = `${shoeData.SKU}_${colorHexToNameMap[defaultColor.toLowerCase()] || "default"
            }`;
          setCurrentImage(imageMap[colorKey] || DefaultShoeImage);

          const availableSizes: number[] = shoeData.COLOR_SIZES.flatMap(
            (item) => item.sizes
          );
          setShoe((prevShoe) => ({
            ...prevShoe!,
            COLOR_SIZES: shoeData.COLOR_SIZES,
            AVAILABLE_SIZES: availableSizes,
          }));
        })
        .catch((err) => console.error("Error fetching shoe details:", err))
        .finally(() => setLoading(false));
    }
  }, [id]);

  const [similarProducts, setSimilarProducts] = useState<Product[]>([]);

  useEffect(() => {
    if (id) {
      axios
        .get(`/api/products/${id}/recommendations`)
        .then((res) => {
          setSimilarProducts(res.data.recommended_products);
        })
        .catch((error) => {
          console.error("Error fetching similar products:", error);
        });
    }
  }, [id]);

  // Handle color change and update available sizes based on selected color
  const handleColorChange = (color: string) => {
    setSelectedColor(color);
    const colorName = colorHexToNameMap[color.toLowerCase()] || "default";

    // Find the available sizes for the selected color
    const colorSizeMapping = shoe?.COLOR_SIZES.find(
      (item) => item.color === color
    );
    if (colorSizeMapping) {
      setSelectedSize(colorSizeMapping.sizes[0]);
    }

    const colorKey = `${shoe?.SKU}_${colorName}`;
    setCurrentImage(imageMap[colorKey] || DefaultShoeImage);

    // Update the available sizes based on the selected color
    setShoe((prevShoe) => ({
      ...prevShoe!,
      AVAILABLE_SIZES: colorSizeMapping ? colorSizeMapping.sizes : [],
    }));
  };

  // Handle size change and enable/disable color based on available sizes for that size
  const handleSizeChange = (size: number) => {
    setSelectedSize(size);

    // Filter colors that are available for the selected size
    const availableColors = shoe?.COLOR_SIZES.filter((item) =>
      item.sizes.includes(size)
    ).map((item) => item.color);

    setShoe((prevShoe) => ({
      ...prevShoe!,
      COLOR_SIZES:
        shoe?.COLOR_SIZES.map((item) => ({
          ...item,
          isAvailable: availableColors
            ? availableColors.includes(item.color)
            : false,
        })) || [],
    }));
  };


  if (!shoe) {
    return (
      <Box className="details-container">
        {" "}
        <Box className="details-image">
          <Skeleton variant="rectangular" width={300} height={300} />{" "}
        </Box>{" "}
        <Box className="details-info">
          <Skeleton width="60%" height={40} />
          <Skeleton width="80%" height={30} />
          <Skeleton width="40%" height={30} />
          <Skeleton width="30%" height={30} />
          <Skeleton width="100%" height={50} sx={{ mt: 2 }} />{" "}
        </Box>{" "}
      </Box>
    );
  }

  return (
    <Box className="details-container">
      <Box className="details-image">
        {currentImage && <img src={currentImage} alt={shoe.PRODUCT_NAME} />}
      </Box>

      <Box className="details-info">
        <Typography variant="h5" fontWeight="bold">
          {shoe.PRODUCT_NAME}
        </Typography>
        <Typography variant="subtitle1" mb={1}>
          {shoe.DESCRIPTION}
        </Typography>
        <Rating value={shoe.RATING} precision={0.5} readOnly />
        <Typography variant="h6" mt={1}>
          ${shoe.PRICE.toFixed(2)}
        </Typography>

        <Typography mt={2} fontWeight="bold">
          SHOE WIDTH
        </Typography>
        <Button variant="outlined" size="small" sx={{ mt: 1 }}>
          Medium
        </Button>

        <Typography mt={2} fontWeight="bold">
          SIZE
        </Typography>
        <Box display="flex" gap={1} flexWrap="wrap" mt={1}>
          {allSizes.map((size) => {
            const isAvailable = shoe?.AVAILABLE_SIZES?.includes(size);
            return (
              <Button
                key={size}
                variant={selectedSize === size ? "outlined" : "text"}
                onClick={() => handleSizeChange(size)}
                disabled={!isAvailable}
                sx={{
                  opacity: isAvailable ? 1 : 0.4,
                  color: "var(--accent-color)",
                  backgroundColor: "var(--bg-color)",
                }}
              >
                {size}
              </Button>
            );
          })}
        </Box>

        <Typography mt={2} fontWeight="bold">
          COLOR
        </Typography>
        <Box display="flex" gap={1} mt={1}>
          {shoe?.COLOR_SIZES.map((colorData) => {
            const isAvailable = colorData.sizes.includes(selectedSize ?? 0);
            const isSelected = selectedColor === colorData.color;

            return (
              <Box
                key={colorData.color}
                onClick={() => handleColorChange(colorData.color)}
                sx={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  backgroundColor: colorData.color,
                  border: isSelected ? "2px solid black" : "1px solid gray",
                  cursor: "pointer",
                  opacity: 1,
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {!isAvailable && (
                  <Box
                    sx={{
                      width: "60%",
                      height: 2,
                      backgroundColor: "#333",
                      transform: "rotate(-45deg)",
                      position: "absolute",
                    }}
                  />
                )}
              </Box>
            );
          })}
        </Box>

        <Typography mt={2} fontWeight="bold">
          QUANTITY
        </Typography>
        <Box display="flex" alignItems="center" gap={2} mt={1}>
          <IconButton onClick={() => setQuantity((q) => Math.max(1, q - 1))}>
            <RemoveIcon />
          </IconButton>
          <Typography>{quantity}</Typography>
          <IconButton onClick={() => setQuantity((q) => q + 1)}>
            <AddIcon />
          </IconButton>
        </Box>

        <Button
          variant="outlined"
          color="primary"
          sx={{ mt: 2, width: "100%" }}
        >
          Add to Cart {" "}
        </Button>
      </Box>

      <Box className="details-similar-products">
        <SimilarProducts productId={id} similarProducts={similarProducts} selectedShoeColor={selectedColor} />
      </Box>
    </Box>
  );
};

export default ShoeDetails;
