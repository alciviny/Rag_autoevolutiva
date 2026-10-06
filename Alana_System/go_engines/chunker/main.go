package main

import (
	"alana_system/go_engines/shared"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// InputChunker representa o texto bruto e os parâmetros de divisão
type InputChunker struct {
	Text         string `json:"text"`
	MaxTokens    int    `json:"max_tokens"` // Estimado por caracteres p/ simplicidade
	OverlapChars int    `json:"overlap_chars"`
}

// ChunkResult representa um pedaço do texto processado
type ChunkResult struct {
	Index   int    `json:"index"`
	Content string `json:"content"`
}

func chunkText(text string, maxChars, overlap int) []ChunkResult {
	textRunes := []rune(text)
	if maxChars < 1 {
		maxChars = 1200
	}
	if overlap < 0 {
		overlap = 0
	} else if overlap >= maxChars {
		overlap = maxChars - 1
	}
	step := maxChars - overlap
	chunks := make([]ChunkResult, 0)
	for start, index := 0, 0; start < len(textRunes); start, index = start+step, index+1 {
		end := start + maxChars
		if end > len(textRunes) {
			end = len(textRunes)
		}
		content := strings.TrimSpace(string(textRunes[start:end]))
		if content != "" {
			chunks = append(chunks, ChunkResult{Index: index, Content: content})
		}
	}
	return chunks
}

func main() {
	// Lê a entrada do Python
	rawInput, err := shared.ReadInput()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Erro na leitura: %v\n", err)
		os.Exit(1)
	}

	var input InputChunker
	if err := json.Unmarshal(rawInput, &input); err != nil {
		fmt.Fprintf(os.Stderr, "Erro no JSON: %v\n", err)
		os.Exit(1)
	}

	chunks := chunkText(input.Text, input.MaxTokens, input.OverlapChars)

	// Devolve o resultado em JSON
	output, _ := json.Marshal(chunks)
	fmt.Print(string(output))
}
