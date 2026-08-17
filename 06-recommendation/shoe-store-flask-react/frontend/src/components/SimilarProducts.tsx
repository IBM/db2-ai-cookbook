import React, { useState, useCallback } from "react";
import { Box, Typography, IconButton, Link } from "@mui/material";
import useEmblaCarousel from "embla-carousel-react";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import "./SimilarProducts.css";

import similarSearch1 from "../assets/similarSearch1.jpeg";
import similarSearch2 from "../assets/similarSearch2.jpeg";
import similarSearch3 from "../assets/similarSearch3.jpeg";
import similarSearch4 from "../assets/similarSearch4.jpeg";
import similarSearch5 from "../assets/similarSearch5.jpeg";
import similarSearch6 from "../assets/similarSearch6.jpeg";
import similarSearch7 from "../assets/similarSearch7.jpeg";
import similarSearch8 from "../assets/similarSearch8.jpeg";


import yellowSimilar1 from "../assets/yellowSimilarShoe1.png";
import yellowSimilar2 from "../assets/yellowSimilarShoe2.png";
import yellowSimilar3 from "../assets/yellowSimilarShoe3.webp";
import yellowSimilar4 from "../assets/yellowSimilarShoe.4.png";
import yellowSimilar5 from "../assets/yellowSimilarShoe5.png";
import yellowSimilar6 from "../assets/yellowSimilarShoe6.webp";
import yellowSimilar7 from "../assets/yellowSimilarShoe7.jpg";
import yellowSimilar8 from "../assets/yellowSimilarShoe.jpeg";


import blackSimilar1 from "../assets/blackSimilarShoe1.webp";
import blackSimilar2 from "../assets/blackSimilarShoe2.jpeg";
import blackSimilar3 from "../assets/blackSimilarShoe3.jpeg";
import blackSimilar4 from "../assets/blackSimilarShoe4.png";
import blackSimilar5 from "../assets/blackSimilarShoe5.png";
import blackSimilar6 from "../assets/blackSimilarShoe6.webp";
import blackSimilar7 from "../assets/blackSimilarShoe7.webp";
import blackSimilar8 from "../assets/blackSimilarShoe8.webp";


import brownSimilar1 from "../assets/brownSimilarShoe1.webp";
import brownSimilar2 from "../assets/brownSimilarShoe2.webp";
import brownSimilar3 from "../assets/brownSimilarShoe3.webp";
import brownSimilar4 from "../assets/brownSimilarShoe4.png";
import brownSimilar5 from "../assets/brownSimilarShoe5.webp";
import brownSimilar6 from "../assets/brownSimilarShoe6.jpg";
import brownSimilar7 from "../assets/brownSimilarShoe7.png";
import brownSimilar8 from "../assets/brownSimilarShoe8.avif";


import greySimilar1 from "../assets/GreySimilarShoe5.png";
import greySimilar2 from "../assets/greySimilarShoe1.png";
import greySimilar3 from "../assets/greySimilarShoe2.png";
import greySimilar4 from "../assets/greySimilarShoe3.jpeg";
import greySimilar5 from "../assets/greySimilarShoe4.jpeg";
import greySimilar6 from "../assets/greySimilarShoe6.webp";
import greySimilar7 from "../assets/greySimilarShoe7.png";
import greySimilar8 from "../assets/greySimilarShoe8.jpeg";



import greenSimilar1 from "../assets/greemSimilarShoe2.png";
import greenSimilar2 from "../assets/greenSimilarShoe1.png";
import greenSimilar3 from "../assets/greenSimilarShoe3.webp";
import greenSimilar4 from "../assets/greenSimilarShoe4.webp";
import greenSimilar5 from "../assets/greenSimilarShoe5.png";
import greenSimilar6 from "../assets/greenSimilarShoe6.png";
import greenSimilar7 from "../assets/greenSimilarShoe7.png";
import greenSimilar8 from "../assets/greenSimilarShoe8.png";

import searchGraph from "../assets/searchGraph.svg";

import ReusableModal from "./ReusableModal";
import ProductDetailModal from "./ProductDetailModal";

interface Product {
  SKU: string;
  PRODUCT_NAME: string;
  PRICE: number;
  BRAND: string;
  COLOR: string;
  RATING: number;
}

interface SimilarProductsProps {
  productId: string | undefined;
  similarProducts: Product[];
  selectedShoeColor: string;
}

const imageSets: Record<string, Record<string, string[]>> = {
  "ZEN-5999": {
    red: [
      similarSearch1,
      similarSearch2,
      similarSearch3,
      similarSearch4,
      similarSearch5,
      similarSearch6,
      similarSearch7,
      similarSearch8,
    ],
    white: [
      similarSearch1,
      similarSearch2,
      similarSearch3,
      similarSearch4,
      similarSearch5,
      similarSearch6,
      similarSearch7,
      similarSearch8,
    ],
    black: [
      blackSimilar1,
      blackSimilar2,
      blackSimilar3,
      blackSimilar4,
      blackSimilar5,
      blackSimilar6,
      blackSimilar7,
      blackSimilar8,
    ],
  },
  "RUN-4723": {
    yellow: [
      yellowSimilar1,
      yellowSimilar2,
      yellowSimilar3,
      yellowSimilar4,
      yellowSimilar5,
      yellowSimilar6,
      yellowSimilar7,
      yellowSimilar8,
    ],
  },
  "ZEN-8968": {
    black: [
      blackSimilar1,
      blackSimilar2,
      blackSimilar3,
      blackSimilar4,
      blackSimilar5,
      blackSimilar6,
      blackSimilar7,
      blackSimilar8,
    ],
    white: [
      greySimilar1,
      greySimilar2,
      greySimilar3,
      greySimilar4,
      greySimilar5,
      greySimilar6,
      greySimilar7,
      greySimilar8,
    ],
  },
  "RUN-7569": {
    black: [ 
      brownSimilar1,
      brownSimilar2,
      brownSimilar3,
      brownSimilar4,
      brownSimilar5,
      brownSimilar6,
      brownSimilar7,
      brownSimilar8,
    ],
  },
  "RUN-1083": {
    white: [
      greySimilar1,
      greySimilar2,
      greySimilar3,
      greySimilar4,
      greySimilar5,
      greySimilar6,
      greySimilar7,
      greySimilar8,
    ],
  },
  "LOO-1505": {
    white: [
      greenSimilar1,
      greenSimilar2,
      greenSimilar3,
      greenSimilar4,
      greenSimilar5,
      greenSimilar6,
      greenSimilar7,
      greenSimilar8,
    ],
  },
};

const colorHexToNameMap: Record<string, string> = {
  "#d90000": "red",
  "#f0f0f0": "white",
  "#ffffff": "white",
  "#000000": "black",
  "#f5c514": "yellow",
  "#e2cbb5": "white",
  "#a52a2a": "brown", 
  "#808080": "grey", 
  "#008000": "green", 
};

const SimilarProducts: React.FC<SimilarProductsProps> = ({
  productId,
  similarProducts,
  selectedShoeColor,
}) => {
  const [emblaRef, emblaApi] = useEmblaCarousel({
    axis: "y",
    loop: true,
    dragFree: false,
  });

  const [isReusableModalOpen, setIsReusableModalOpen] = useState(false);
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [selectedProductImage, setSelectedProductImage] = useState<string>("");

  const handleOpenReusableModal = () => {
    setIsReusableModalOpen(true);
  };

  const handleCloseReusableModal = () => {
    setIsReusableModalOpen(false);
  };

  const handleOpenProductModal = (product: Product, imageUrl: string) => {
    setSelectedProduct(product);
    setSelectedProductImage(imageUrl);
    setIsProductModalOpen(true);
  };

  const handleCloseProductModal = () => {
    setIsProductModalOpen(false);
    setSelectedProduct(null);
    setSelectedProductImage("");
  };

  const handleScrollPrev = useCallback(() => {
    if (emblaApi) emblaApi.scrollPrev();
  }, [emblaApi]);

  const handleScrollNext = useCallback(() => {
    if (emblaApi) emblaApi.scrollNext();
  }, [emblaApi]);

  return (
    <Box className="similar-products-container">
      <Typography variant="h5" fontWeight="bold" mb={2}>
        YOU MAY ALSO LIKE
      </Typography>
      <Link
        component="button"
        onClick={handleOpenReusableModal}
        underline="hover"
        color="text.secondary"
        sx={{
          mb: 2,
          display: "inline-block",
          fontSize: 14,
          color: "var(--text-color)",
        }}
      >
        Powered by IBM Db2
      </Link>
      <Box className="carousel-controls">
        <IconButton onClick={handleScrollPrev}>
          <ArrowUpwardIcon sx={{ color: "var(--text-color)" }} />
        </IconButton>
        <IconButton onClick={handleScrollNext}>
          <ArrowDownwardIcon sx={{ color: "var(--text-color)" }} />
        </IconButton>
      </Box>
      <Box className="embla" ref={emblaRef}>
        <Box className="embla__container">
          {similarProducts.map((product, index) => {
            const mainShoeSKUPrefix = productId ? productId.split("_")[0] : "";
            const selectedColorName =
              colorHexToNameMap[selectedShoeColor.toLowerCase()];

            let imageUrl: string = "";

            if (
              mainShoeSKUPrefix &&
              selectedColorName &&
              imageSets[mainShoeSKUPrefix]?.[selectedColorName]?.[index]
            ) {
              imageUrl =
                imageSets[mainShoeSKUPrefix][selectedColorName][index];
            } else {
              const productSKUPrefix = product.SKU.split("_")[0];
              const productColorName =
                colorHexToNameMap[product.COLOR.toLowerCase()];

              if (
                productSKUPrefix &&
                productColorName &&
                imageSets[productSKUPrefix]?.[productColorName]?.[index]
              ) {
                imageUrl =
                  imageSets[productSKUPrefix][productColorName][index];
              } else {
                imageUrl = similarSearch1;
              }
            }

            return (
              <Box
                className="embla__slide"
                key={product.SKU}
                onClick={() => handleOpenProductModal(product, imageUrl)}
                sx={{ cursor: "pointer" }}
              >
                <img
                  src={imageUrl}
                  alt={product.PRODUCT_NAME}
                  className="product-image"
                />
                <Typography variant="body1" className="product-name">
                  {product.PRODUCT_NAME}
                </Typography>
              </Box>
            );
          })}
        </Box>
      </Box>
      <ReusableModal
        open={isReusableModalOpen}
        onClose={handleCloseReusableModal}
        stepTitles={["Query for Vector Search", "Vector Search Visualization"]}
        sqlQuery={`SELECT
  sku,
  PRODUCT_NAME,
  BRAND,
  PRICE,
  RATING,
  COLOR,
  vector_distance(
    (SELECT embedding FROM s1.sq_shoes WHERE sku = ?),
    embedding,
    euclidean) AS distance
  FROM s1.sq_shoes
  WHERE sku <> ?
  ORDER BY distance ASC
  FETCH FIRST 8 ROWS ONLY`}
        imageUrl={searchGraph}
      />

      <ProductDetailModal
        open={isProductModalOpen}
        onClose={handleCloseProductModal}
        product={selectedProduct}
        imageUrl={selectedProductImage}
      />
    </Box>
  );
};

export default SimilarProducts;