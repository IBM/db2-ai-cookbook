import React, { useState } from "react";
import {
  Modal,
  Box,
  Typography,
  IconButton,
  Button,
  Fade,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { useTheme } from "../context/ThemeContext";

interface ReusableModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  sqlQuery: string;
  imageUrl: string;
  stepTitles?: string[]; // NEW
}

const ReusableModal: React.FC<ReusableModalProps> = ({
  open,
  onClose,
  title,
  sqlQuery,
  imageUrl,
  stepTitles,
}) => {
  const [step, setStep] = useState(1);

  const handleNext = () => {
    setStep((prev) => prev + 1);
  };

  const { theme } = useTheme();

  const handleBack = () => {
    setStep((prev) => prev - 1);
  };

  const handleClose = () => {
    setStep(1); // Reset to step 1 when closing
    onClose();
  };

  return (
    <Modal open={open} onClose={handleClose}>
      <Fade in={open}>
        <Box
          sx={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            width: { xs: 320, sm: 520 },
            bgcolor: "var(--bg-color)",
            boxShadow: 24,
            p: 4,
            borderRadius: 3,
            outline: "none",
          }}
        >
          <Box
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            mb={2}
          >
            <Typography variant="h6" fontWeight="bold">
              {stepTitles?.[step - 1] || title} (Step {step}/2)
            </Typography>
            <IconButton onClick={handleClose} size="small">
              <CloseIcon />
            </IconButton>
          </Box>

          {step === 1 && (
            <Box
              sx={{
                backgroundColor: theme === "dark" ? "#1e1e1e" : "#f5f5f5",
                color: theme === "dark" ? "#f5f5f5" : "#000000",
                p: 2,
                borderRadius: 2,
                overflowX: "auto",
                fontFamily: "monospace",
                fontSize: "0.9rem",
                whiteSpace: "pre-wrap",
                minHeight: 150,
              }}
            > 
            {/* 180012009009,  912230430101 */}
              {sqlQuery}
            </Box>
          )}

          {step === 2 && (
            <Box
              sx={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                minHeight: 200,
                borderRadius: 2,
                overflow: "hidden",
                boxShadow: 3,
              }}
            >
              <img
                src={imageUrl}
                alt="Step 2 visual"
                style={{
                  width: "100%",
                  height: "auto",
                  transition: "transform 0.5s",
                }}
                onMouseOver={(e) =>
                  (e.currentTarget.style.transform = "scale(1)")
                }
                onMouseOut={(e) =>
                  (e.currentTarget.style.transform = "scale(1)")
                }
              />
            </Box>
          )}

          <Box display="flex" justifyContent="space-between" mt={3}>
            {step > 1 && (
              <Button variant="outlined" onClick={handleBack}>
                Back
              </Button>
            )}
            {step < 2 && (
              <Button variant="contained" onClick={handleNext}>
                View Graph
              </Button>
            )}
          </Box>
        </Box>
      </Fade>
    </Modal>
  );
};

export default ReusableModal;
