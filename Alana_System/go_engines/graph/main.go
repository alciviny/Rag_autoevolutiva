package main

import (
	"alana_system/go_engines/shared"
	"encoding/json"
	"fmt"
	"os"
	"sync"
)

// Edge representa uma conexão no grafo
type Edge struct {
	From string `json:"from"`
	To   string `json:"to"`
	Type string `json:"type"`
}

// GraphInput representa os dados enviados pelo Python
type GraphInput struct {
	Edges  []Edge `json:"edges"`
	Source string `json:"source"`
	Target string `json:"target"`
	Mode   string `json:"mode"` // "path", "neighbors", "density"
	Hops   int    `json:"hops"`
}

// Neighbors retorna os nós alcançáveis em até hops arestas, sem duplicatas.
func (g *GraphEngine) Neighbors(start string, hops int) []string {
	if hops < 1 {
		hops = 1
	}
	visited := map[string]bool{start: true}
	frontier := []string{start}
	result := make([]string, 0)
	for depth := 0; depth < hops && len(frontier) > 0; depth++ {
		next := make([]string, 0)
		for _, node := range frontier {
			for _, neighbor := range g.Adjacency[node] {
				if !visited[neighbor] {
					visited[neighbor] = true
					result = append(result, neighbor)
					next = append(next, neighbor)
				}
			}
		}
		frontier = next
	}
	return result
}

// GraphEngine gerencia a estrutura de adjacência
type GraphEngine struct {
	Adjacency map[string][]string
	mu        sync.RWMutex
}

func NewGraphEngine(edges []Edge) *GraphEngine {
	engine := &GraphEngine{
		Adjacency: make(map[string][]string),
	}
	for _, edge := range edges {
		engine.Adjacency[edge.From] = append(engine.Adjacency[edge.From], edge.To)
		// Se for não-direcionado, descomente:
		// engine.Adjacency[edge.To] = append(engine.Adjacency[edge.To], edge.From)
	}
	return engine
}

// FindPath busca o caminho mais curto entre dois nós (BFS)
func (g *GraphEngine) FindPath(start, end string) []string {
	if start == end {
		return []string{start}
	}

	queue := [][]string{{start}}
	visited := map[string]bool{start: true}

	for len(queue) > 0 {
		path := queue[0]
		queue = queue[1:]
		node := path[len(path)-1]

		for _, neighbor := range g.Adjacency[node] {
			if neighbor == end {
				return append(path, end)
			}
			if !visited[neighbor] {
				visited[neighbor] = true
				newPath := append([]string{}, path...)
				newPath = append(newPath, neighbor)
				queue = append(queue, newPath)
			}
		}
	}
	return nil
}

func main() {
	rawInput, err := shared.ReadInput()
	if err != nil {
		fmt.Fprint(os.Stderr, err)
		os.Exit(1)
	}
	var input GraphInput
	if err := json.Unmarshal(rawInput, &input); err != nil {
		fmt.Fprint(os.Stderr, err)
		os.Exit(2)
	}

	engine := NewGraphEngine(input.Edges)

	var result interface{}

	switch input.Mode {
	case "path":
		result = engine.FindPath(input.Source, input.Target)
	case "neighbors":
		hops := input.Hops
		if hops < 1 {
			hops = 1
		} else if hops > 5 {
			hops = 5
		}
		result = engine.Neighbors(input.Source, hops)
	case "density":
		result = len(input.Edges)
	}

	output, _ := json.Marshal(result)
	fmt.Print(string(output))
}
